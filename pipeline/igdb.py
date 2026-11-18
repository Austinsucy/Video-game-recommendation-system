"""
Reading the IGDB dataset and turning one IGDB game into our shape.

The goal is that a game looks the same in our database no matter which
dataset it came from: same columns, same feature vocabulary, same coverage
rows. Everything IGDB-specific (which column feeds which field, which
platform names count as PC) is in map_config.yaml under sources.igdb, so
this file is only mechanism, like ingest.py.

The functions here are used by pipeline/ingest.py. Nothing in this file
writes to the database.
"""
from __future__ import annotations

import json
from collections import Counter
from functools import lru_cache
from pathlib import Path

import pandas as pd

from backend.app.models import VALID_CATEGORIES
from pipeline.cleaning import (
    clean_display_title,
    clean_html_text,
    clean_list,
    clean_summary,
    compile_patterns,
    is_blank,
    json_list,
    non_game_match,
    short_summary,
)
from pipeline.config import map_raw_tag

# The IGDB lists that act like tags: they describe the game, they are not
# its genre or platform. A game with any of these has tag_source 'igdb'.
TAG_LIKE_FIELDS = ("themes", "keywords", "player_perspectives", "game_modes")


# ===========================================================================
# PART 1: reading and cleaning the file
# ===========================================================================

def read_igdb(cfg: dict, csv_path: Path) -> tuple[pd.DataFrame, dict]:
    """Read the IGDB CSV and clean it. Returns the rows and a funnel of counts."""
    ig = cfg["sources"]["igdb"]
    df = pd.read_csv(csv_path, low_memory=False)
    stats = {"rows_in_file": len(df)}

    # The IGDB file writes "Missing" where it has no name. Those are not games
    # we can show or match. (A real game can be called "None", so only this
    # exact placeholder and true blanks count.)
    bad_name = df["name"].isna() | df["name"].astype(str).str.strip().isin(["", "Missing"])
    stats["dropped_no_name"] = int(bad_name.sum())
    df = df[~bad_name]

    dropped = df["category"].isin(ig.get("drop_categories") or [])
    stats["dropped_categories"] = df.loc[dropped, "category"].value_counts().to_dict()
    df = df[~dropped]

    suffixes = tuple(ig.get("rejoin_suffixes") or ())
    company_columns = set(ig.get("company_columns") or [])
    for column in ig["list_columns"]:
        use = suffixes if column in company_columns else ()
        df[column] = df[column].map(lambda v, use=use: clean_list(v, use))

    for column in ig.get("zero_is_missing") or []:
        df[column] = pd.to_numeric(df[column], errors="coerce").replace(0, pd.NA)

    # Sorted by IGDB id: new games get our ids in this order (REL 2).
    df = df.sort_values("id", kind="mergesort").reset_index(drop=True)
    df["igdb_id"] = df["id"].astype(int)
    stats["after_cleaning"] = len(df)
    return df, stats


# ===========================================================================
# PART 2: one IGDB game -> one `games` row
# ===========================================================================

def _iso(value):
    from pipeline.ingest import iso_date
    return iso_date(value) if not is_blank(value) else None


def _year(value):
    from pipeline.ingest import year_from_date
    return year_from_date(value) if not is_blank(value) else None


def _number(value):
    parsed = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(parsed) else float(parsed)


def igdb_transforms(ig: dict) -> dict:
    """The conversions an IGDB column can ask for, with the config's limits filled in."""
    from pipeline.ingest import normalise_title

    min_chars = int(ig.get("min_summary_chars", 15))
    limit = int(ig.get("short_description_chars", 350))
    return {
        "clean_text": lambda v: None if is_blank(v) else str(v).strip(),
        "clean_display_title": clean_display_title,
        "clean_html_text": clean_html_text,
        "normalise_title": normalise_title,
        "iso_date": _iso,
        "year_from_date": _year,
        "short_summary": lambda v: short_summary(v, limit, min_chars),
        "clean_summary": lambda v: clean_summary(v, min_chars),
        # Lists arrive already cleaned by read_igdb.
        "join_list": lambda v: ", ".join(v) if isinstance(v, list) and v else None,
        "first_list_item": lambda v: v[0] if isinstance(v, list) and v else None,
        "number": _number,
    }


@lru_cache(maxsize=8)
def _compiled(patterns: tuple[str, ...]):
    return compile_patterns(patterns)


def build_igdb_row(rec: dict, cfg: dict, game_id: int) -> dict:
    """Build a `games` row for an IGDB game that has no Steam match."""
    ig = cfg["sources"]["igdb"]
    transforms = igdb_transforms(ig)
    row = {"game_id": game_id}
    for column, spec in ig["column_sources"].items():
        value = rec.get(spec["from"])
        fn = transforms[spec["transform"]] if spec.get("transform") else transforms["clean_text"]
        result = fn(value)
        if result is None and spec.get("fallback"):
            fallback = rec.get(spec["fallback"])
            result = transforms["clean_text"](fallback)
        row[column] = result

    # Columns IGDB simply does not have.
    for column in ("store_url", "playtime_hours", "rating_count", "popularity",
                   "popularity_source", "raw_tags_json"):
        row[column] = None

    has_rating = row.get("rating") is not None
    row["rating_kind"] = ig["rating_kind"] if has_rating else None
    row["rating_scale"] = ig["rating_scale"] if has_rating else None
    if row.get("release_year") is not None:
        row["release_year"] = int(row["release_year"])

    row["platforms_raw"] = json_list(rec.get("platforms") or [])
    row["primary_source"] = "igdb"
    row["is_adult"] = int(bool(set(rec.get("themes") or []) & set(ig.get("adult_markers") or [])))
    row["is_non_game"] = int(non_game_match(row["title"], _compiled(tuple(cfg.get("non_game_patterns") or []))) is not None)
    row["is_upcoming"] = int(bool(row.get("release_date")) and row["release_date"] > str(ig["upcoming_after"]))
    has_tags = any(rec.get(f) for f in TAG_LIKE_FIELDS)
    row["tag_source"] = "igdb" if has_tags else "none"
    row["raw_tags_kind"] = "presence" if has_tags else None
    # The IGDB blurb goes in too. A merged Steam game keeps Steam's
    # description in games.description, so without this the IGDB text would
    # be lost, and map v4 learns from exactly that text (pipeline/translate.py).
    row["raw_igdb_json"] = raw_igdb_json(rec, ig, {"description": row.get("description")})
    return row


def raw_igdb_json(rec: dict, ig: dict, extra: dict | None = None) -> str | None:
    """The IGDB lists exactly as the file had them (after the list clean-up).

    `extra` adds values we worked out ourselves, like the short description.
    """
    out = {key: value for key, value in (extra or {}).items() if value is not None}
    for column in ig.get("raw_columns") or []:
        value = rec.get(column)
        if isinstance(value, list):
            if value:
                out[column] = value
        elif value is not None and not (isinstance(value, float) and pd.isna(value)) and value is not pd.NA:
            out[column] = value.item() if hasattr(value, "item") else value
    return json.dumps(out, ensure_ascii=False, sort_keys=True) if out else None


# Columns IGDB may fill on a merged Steam game, but only when Steam left
# them empty. Grouped so values that belong together are filled together
# (a date with its year, a rating with what kind of rating it is).
FILL_GROUPS = (
    ("description",),
    ("long_description",),
    ("developers",),
    ("publishers",),
    ("release_date", "release_year"),
    ("cover_image_url",),
    ("header_image_url",),
    ("rating", "rating_kind", "rating_scale"),
)


def merge_into_steam(steam_row: dict, igdb_row: dict) -> list[str]:
    """Fill a Steam game's EMPTY columns from its IGDB match. Steam always wins.

    Changes steam_row in place and returns the list of columns it filled,
    so the report can count them.
    """
    filled = []
    for group in FILL_GROUPS:
        lead = group[0]
        if steam_row.get(lead) is None and igdb_row.get(lead) is not None:
            for column in group:
                steam_row[column] = igdb_row.get(column)
            filled.append(lead)

    # Platforms: Steam's list first, then anything IGDB adds.
    steam_platforms = json.loads(steam_row["platforms_raw"]) if steam_row.get("platforms_raw") else []
    igdb_platforms = json.loads(igdb_row["platforms_raw"]) if igdb_row.get("platforms_raw") else []
    combined = steam_platforms + [p for p in igdb_platforms if p not in steam_platforms]
    steam_row["platforms_raw"] = json_list(combined)

    steam_row["is_adult"] = int(steam_row["is_adult"] or igdb_row["is_adult"])
    steam_row["raw_igdb_json"] = igdb_row["raw_igdb_json"]
    # A Steam game with no tags of its own now gets IGDB's (presence only,
    # never fake vote counts: raw_tags_json stays NULL).
    if steam_row["tag_source"] == "none" and igdb_row["tag_source"] == "igdb":
        steam_row["tag_source"] = "igdb"
        steam_row["raw_tags_kind"] = "presence"
        filled.append("tags")
    return filled


# ===========================================================================
# PART 3: features
# ===========================================================================

def platform_lookup(ig: dict) -> dict[str, str]:
    """IGDB platform name -> platform family feature name. Exact names only."""
    return {name: family for family, names in ig["platform_families"].items() for name in names}


def resolve_igdb_features(rec: dict, cfg: dict, aliases: dict, registry, platforms: dict[str, str]):
    """Every feature an IGDB game gets, plus its nine coverage verdicts.

    Same rules as Steam (resolve_features in ingest.py): an alias makes a
    weighted feature, anything else becomes a display-only tag, and a raw
    string never becomes both.
    """
    ig = cfg["sources"]["igdb"]
    demoted = set(ig.get("demote_genres_to_tags") or [])
    found: set[tuple[str, str]] = set()

    genres = rec.get("genres") or []
    for raw in genres:
        found.add(registry.ensure_tag(raw) if raw in demoted else registry.resolve(raw, aliases))
    for column in TAG_LIKE_FIELDS:
        for raw in rec.get(column) or []:
            found.add(registry.resolve(raw, aliases))
    plats = rec.get("platforms") or []
    for raw in plats:
        family = platforms.get(raw)
        if family and ("platform", family) in registry.approved:
            found.add(("platform", family))

    themes_or_keywords = bool(rec.get("themes") or rec.get("keywords"))
    had = {
        "genre": bool(genres),
        "multiplayer": bool(rec.get("game_modes")),
        "platform": bool(plats),
        "tag": themes_or_keywords,
        "perspective": bool(rec.get("player_perspectives")) or themes_or_keywords,
        "gameplay": themes_or_keywords,
        "mechanic": themes_or_keywords,
        "structure": themes_or_keywords,
        "theme": themes_or_keywords,
    }
    present = {category for category, _ in found}
    coverage = {}
    for category in VALID_CATEGORIES:
        coverage[category] = ("present" if category in present
                              else "absent" if had[category] else "unknown")
    return found, coverage


def alias_coverage(df: pd.DataFrame, cfg: dict, aliases: dict, approved: set) -> dict:
    """For each IGDB list, what share of its values reach a weighted feature.

    Values demoted to tags on purpose ("Indie") are taken out of the count,
    because leaving them as tags is a decision, not a gap.
    """
    ig = cfg["sources"]["igdb"]
    demoted = set(ig.get("demote_genres_to_tags") or [])
    out = {}
    for column in ("genres", "themes", "player_perspectives", "game_modes", "keywords"):
        counts = Counter(v for items in df[column] for v in items)
        total = sum(counts.values())
        demoted_n = sum(n for v, n in counts.items() if column == "genres" and v in demoted)
        hit = sum(n for v, n in counts.items()
                  if not (column == "genres" and v in demoted)
                  and map_raw_tag(v, aliases) in approved
                  and map_raw_tag(v, aliases)[0] != "tag")
        unmapped = Counter({v: n for v, n in counts.items()
                            if not (column == "genres" and v in demoted)
                            and not (map_raw_tag(v, aliases) in approved and map_raw_tag(v, aliases)[0] != "tag")})
        denominator = total - demoted_n
        out[column] = {
            "values": total, "demoted": demoted_n, "mapped": hit,
            "share": (hit / denominator) if denominator else 1.0,
            "top_unmapped": unmapped.most_common(30),
        }
    return out


def igdb_feature_stats(rec: dict) -> int:
    """How many tag-like values IGDB has for a game (themes, keywords, perspectives, modes)."""
    return sum(len(rec.get(f) or []) for f in TAG_LIKE_FIELDS)
