"""
THE IMPORT: turns the raw Steam CSV into our database.

WHAT THIS DOES, IN ORDER
    1. read the CSV (only the columns the config says we need)
    2. throw out games that do not meet our minimum standards
    3. sort them and keep the top N
    4. turn each game's genres / categories / tags into features
    5. write everything to the database in one transaction
    6. print a report of what happened

HOW TO RUN IT (from the repo root, with your venv active)
    python -m pipeline.ingest              normal run
    python -m pipeline.ingest --reset      wipe and rebuild
    python -m pipeline.ingest --limit 40   small run for testing

IMPORTANT IDEA
    This file contains no decisions, only mechanism. Which games we pick,
    which CSV column becomes which database column, which tag counts as which
    feature: all of that lives in config/map_config.yaml. That is our MAINT 2
    requirement, and it means Austin and Kayne can retune everything without
    touching Python.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import delete, func, select

from backend.app.db import SessionLocal
from backend.app.models import (
    VALID_CATEGORIES,
    Feature,
    Game,
    GameFeature,
    GameFeatureCoverage,
    GameSource,
    MapVersion,
)
from pipeline.config import (
    REPO_ROOT,
    alias_lookup,
    csv_columns_needed,
    load_config,
    map_raw_tag,
    slugify,
)

# The five categories Steam has no column for. We have to dig these out of the
# tag list using the alias map, which is why they are grouped together here:
# if a game has no tags at all, all five are "unknown" rather than "absent".
TAG_DERIVED_CATEGORIES = ("gameplay", "mechanic", "structure", "theme", "perspective")


# ===========================================================================
# PART 1: small helpers for cleaning up messy values
# ===========================================================================

def clean_text(value) -> str | None:
    """Trim whitespace. Turn blanks and pandas NaN into None (SQL NULL).

    Needed because the CSV mixes real missing values with empty strings, and
    we want both to end up as NULL rather than one of them being an empty
    string that looks like real data.
    """
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def normalise_title(value) -> str:
    """Make a searchable version of a title.

    "The Witcher 3: Wild Hunt"  ->  "the witcher 3 wild hunt"

    The \\w character class is Unicode-aware, which matters a lot here. An
    earlier version used [a-z0-9] and it blanked out every Chinese and
    Japanese title in the dataset, making them all look like duplicates of
    each other. Worth remembering if you ever touch this.
    """
    original = str(value).strip().lower()
    text = re.sub(r"[^\w\s]+", " ", original, flags=re.UNICODE)
    text = re.sub(r"_+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Some games are titled with nothing BUT punctuation or symbols. The full
    # catalogue has four: "***", ".", "..." and "∞". Stripping punctuation
    # leaves those as an empty string, which breaks search and makes all four
    # look like duplicates of each other. So if cleaning wipes out the whole
    # title, we fall back to the plain lowercased version instead.
    return text or original


def year_from_date(value) -> int | None:
    """Pull just the year out of a date string like '2015-05-18'."""
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else int(parsed.year)


def iso_date(value) -> str | None:
    """Tidy a date into "YYYY-MM-DD", or None if it cannot be read.

    Our source already uses this format, but we parse and re-format anyway so
    that a future data source with a different style (say "18 May, 2015")
    still lands in the database the same way. SQLite has no real date type,
    so a consistent string is what makes dates sortable and comparable.
    """
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.strftime("%Y-%m-%d")


def join_list(value) -> str | None:
    """Turn ['Rockstar North'] or ['A', 'B'] into readable text.

    Used for developers and publishers. Most games have exactly one, but
    around 8% have several and one has 41, so we join rather than assuming
    the first is the only one that matters.

    Duplicates are removed while keeping the original order, because the
    source occasionally lists the same studio twice.
    """
    items = as_list(value)
    seen: list[str] = []
    for item in items:
        cleaned = str(item).strip()
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return ", ".join(seen) or None


def minutes_to_hours(value) -> float | None:
    """Steam reports playtime in minutes. We store hours."""
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return None
    return round(float(number) / 60.0, 2)


def json_dump(value) -> str | None:
    """Store a parsed value back as JSON text, for the raw tags column."""
    parsed = parse_cell(value)
    if not parsed:
        return None
    return json.dumps(parsed, ensure_ascii=False)


def parse_cell(value):
    """Read one cell that holds a Python literal.

    This CSV stores lists and dicts as their Python repr, so a cell can
    literally contain the text  ['Action', 'Indie']  or
    {'FPS': 90857, 'Shooter': 65397}. literal_eval turns that back into a real
    list or dict. It is the safe version of eval: it only understands literals,
    so a malicious cell cannot run code.
    """
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text[0] in "[{":
        try:
            return ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return None
    # Not a literal, so treat it as a plain comma-separated list.
    return [part.strip() for part in text.split(",") if part.strip()]


def as_list(value) -> list[str]:
    """Get a plain list of strings out of a cell, whatever shape it is in.

    For the tags column this returns just the tag NAMES and drops the vote
    counts. That is fine here, because the full object with counts is saved
    separately in games.raw_tags_json.
    """
    parsed = parse_cell(value)
    if isinstance(parsed, dict):
        return [str(key) for key in parsed]
    if isinstance(parsed, list):
        return [str(item) for item in parsed]
    return []


def numeric_or_none(value, zero_means_missing: bool = False):
    """Convert to a number, with an option to treat 0 as missing.

    That option exists because Steam writes 0 where it means "we have no
    data". A metacritic score of 0 does not mean the game scored zero, it
    means nobody scored it. 96% of games are like that. If we stored those
    zeros, every average we ever calculate would be wrong.
    """
    number = pd.to_numeric(value, errors="coerce")
    if pd.isna(number):
        return None
    number = float(number)
    if zero_means_missing and number == 0.0:
        return None
    return number


def sha256_file(path: Path) -> str:
    """Fingerprint the source file so we can prove which data built a map.

    Read in 1 MB chunks rather than all at once, because the file is 447 MB
    and loading it into memory just to hash it would be wasteful.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# Look-up table so the config can name a transform as a string.
TRANSFORMS = {
    "clean_text": clean_text,
    "normalise_title": normalise_title,
    "year_from_date": year_from_date,
    "iso_date": iso_date,
    "join_list": join_list,
    "minutes_to_hours": minutes_to_hours,
    "json_dump": json_dump,
}


# ===========================================================================
# PART 2: choosing which games to import
# ===========================================================================

def select_games(cfg: dict, csv_path: Path, limit: int | None = None):
    """Narrow 89,618 games down to the ~1,000 we actually want.

    Returns the chosen rows plus a dict of counts, so the report can show how
    many games each filter removed. That breakdown is genuinely useful: if we
    end up with fewer games than expected, it tells you which rule to loosen.
    """
    sel = cfg["selection"]
    # target_count can be null, which means "no limit". Only mode: all allows
    # that, and pipeline/config.py already checked it.
    target = limit if limit is not None else sel.get("target_count")

    # Only read the columns the config actually references. On a 447 MB file
    # this is the difference between a few seconds and a lot of wasted memory.
    columns = csv_columns_needed(cfg)
    df = pd.read_csv(csv_path, usecols=columns, low_memory=False)
    stats = {"rows_in_file": len(df)}

    # --- drop rows with no usable name ---
    df["name"] = df["name"].astype(str).str.strip()
    df = df[(df["name"] != "") & (df["name"].str.lower() != "nan")]

    df["release_year"] = df["release_date"].apply(year_from_date)
    df["genre_list"] = df["genres"].apply(as_list)
    df["tag_list"] = df["tags"].apply(as_list)

    excluded = set(sel.get("exclude_genres") or [])
    demoted = set(sel.get("demote_genres_to_tags") or [])

    # --- drop non-game software, if the config asks us to ---
    if excluded:
        df = df[~df["genre_list"].apply(lambda gs: bool(excluded & set(gs)))]
    stats["after_genre_exclusions"] = len(df)

    # Count only genres that will really become genre features. "Indie" is in
    # Steam's genres column but we demote it to a tag, so a game whose only
    # genre is "Indie" should NOT pass the min_genres check.
    df["real_genres"] = df["genre_list"].apply(
        lambda gs: [g for g in gs if g not in demoted]
    )

    df = df[df["release_year"].notna()]
    stats["with_release_year"] = len(df)

    # --- year window ---
    # mode: all skips this entirely and keeps every year.
    mode = sel["mode"]
    if mode == "popular_pre2019":
        df = df[df["release_year"] <= sel["max_year"]]
    elif mode == "popular_recent":
        df = df[df["release_year"] >= sel["min_year"]]
    stats["after_year_filter"] = len(df)
    stats["selection_mode"] = mode

    # --- DATA 1 minimums ---
    df = df[df["real_genres"].str.len() >= sel["min_genres"]]
    stats["with_min_genres"] = len(df)

    df = df[df["tag_list"].str.len() >= sel["min_tags"]]
    stats["with_min_tags"] = len(df)

    # --- sort and take the top N ---
    # Two sort keys, not one. Review count alone would leave ties in whatever
    # order pandas happened to produce, and two people running this could get
    # different games. Adding title as a tie-breaker makes it deterministic,
    # which REL 2 requires.
    #
    # mergesort is specified because it is stable; the default sort is not.
    rank_column = sel["rank_by"]
    df["_rank"] = pd.to_numeric(df[rank_column], errors="coerce").fillna(0)
    df = df.sort_values(["_rank", "name"], ascending=[False, True], kind="mergesort")

    stats["eligible_pool"] = len(df)
    # No target means keep everything that got this far.
    chosen = (df if target is None else df.head(target)).copy().drop(columns=["_rank"])
    stats["selected"] = len(chosen)
    return chosen, stats


# ===========================================================================
# PART 3: turning raw text into features
# ===========================================================================

class FeatureRegistry:
    """Keeps track of every feature we are going to write to the database.

    Starts out holding the approved vocabulary from the config. As the import
    runs, any raw tag that has no alias gets added as a display-only `tag`
    feature, so nothing from the source is ever lost.
    """

    def __init__(self, cfg: dict):
        self.rows: dict[tuple[str, str], str] = {}
        for category, entries in cfg["vocabulary"].items():
            for entry in entries:
                self.rows[(category, entry["name"])] = entry["display_name"]

        # A snapshot of what came from the config, so we can tell config
        # features apart from ones we invented while importing.
        self.approved = set(self.rows)

    def ensure_tag(self, raw: str) -> tuple[str, str]:
        """Get (or create) a display-only tag feature for some raw text."""
        key = ("tag", slugify(raw))
        if key not in self.rows:
            self.rows[key] = str(raw).strip()
        return key

    def resolve(self, raw: str, aliases: dict[str, tuple[str, str]]) -> tuple[str, str]:
        """The feature a raw genre or tag becomes: its alias if approved, else a display tag.

        map_raw_tag lives in pipeline/config.py so the vectorizer and the
        importer agree exactly on how a Steam tag maps to a feature.
        """
        key = map_raw_tag(raw, aliases)
        return key if key in self.approved else self.ensure_tag(raw)


def resolve_features(row, cfg: dict, aliases: dict, registry: FeatureRegistry):
    """Work out every feature one game should have.

    Returns two things:
      found     a set of (category, name) pairs
      coverage  what we can honestly say about each of the nine categories

    The key rule: if a raw string matches an alias, it becomes that weighted
    feature and does NOT also become a tag. Otherwise "Open World" would be
    counted twice, once as a structure feature and once as a tag, which is
    exactly what our scrum doc warns against.
    """
    sel = cfg["selection"]
    demoted = set(sel.get("demote_genres_to_tags") or [])
    multiplayer_map = sel.get("multiplayer_categories") or {}

    found: set[tuple[str, str]] = set()

    # --- genres column ---
    genres_raw = row["genre_list"]
    for raw in genres_raw:
        if raw in demoted:
            # Content warnings and business models: keep them, but as tags.
            found.add(registry.ensure_tag(raw))
            continue
        found.add(registry.resolve(raw, aliases))

    # --- categories column, which tells us about multiplayer ---
    categories_raw = as_list(row["categories"])
    for raw in categories_raw:
        name = multiplayer_map.get(raw)
        if name and ("multiplayer", name) in registry.approved:
            found.add(("multiplayer", name))

    # --- the three platform booleans ---
    for column, feature_name in (("windows", "windows"),
                                 ("mac", "macos"),
                                 ("linux", "linux")):
        if bool(row[column]) and ("platform", feature_name) in registry.approved:
            found.add(("platform", feature_name))

    # --- tags: where most features actually come from ---
    tags_raw = row["tag_list"]
    for raw in tags_raw:
        found.add(registry.resolve(raw, aliases))

    # --- coverage: what can we honestly claim about each category? ---
    present_categories = {category for category, _ in found}

    # Did the source give us anything at all to judge this category on?
    source_had_something = {
        "genre": bool(genres_raw),
        "multiplayer": bool(categories_raw),
        "platform": True,             # the booleans are always present
        "tag": bool(tags_raw),
        **{category: bool(tags_raw) for category in TAG_DERIVED_CATEGORIES},
    }

    coverage = {}
    for category in VALID_CATEGORIES:
        if category in present_categories:
            coverage[category] = "present"
        elif source_had_something.get(category):
            # We had data, nothing matched. A real absence, as far as our
            # current vocabulary can tell.
            coverage[category] = "absent"
        else:
            # No data to go on. Different from a real absence.
            coverage[category] = "unknown"

    return found, coverage


# ===========================================================================
# PART 4: the main import
# ===========================================================================

def build_game_row(raw_row: dict, cfg: dict, game_id: int) -> dict:
    """Build one row for the `games` table, driven entirely by the config.

    Every column in fields.column_sources gets built here. Nothing is
    hardcoded, so adding a column to the config adds it to the database
    without touching this function.
    """
    sources = cfg["fields"]["column_sources"]
    store_template = cfg["dataset"]["store_url_template"]

    row = {"game_id": game_id}

    for column, spec in sources.items():
        value = raw_row.get(spec["from"])

        # If the main column is empty and a fallback is configured, try that.
        if (value is None or pd.isna(value)) and spec.get("fallback"):
            value = raw_row.get(spec["fallback"])

        transform_name = spec.get("transform")

        # store_url is special: it builds a URL rather than converting a value.
        if transform_name == "store_url_template":
            row[column] = store_template.format(appid=str(int(raw_row["appid"])))
            continue

        if spec.get("zero_is_missing"):
            value = numeric_or_none(value, zero_means_missing=True)

        if transform_name:
            row[column] = TRANSFORMS[transform_name](value)
        else:
            number = numeric_or_none(value)
            row[column] = number if number is not None else clean_text(value)

    # rating_scale is not read from the CSV, it describes what `rating` means.
    # Only set it when there is actually a rating to describe.
    row["rating_scale"] = cfg["fields"]["rating_scale"] if row.get("rating") is not None else None

    # These two are whole numbers, not floats.
    if row.get("release_year") is not None:
        row["release_year"] = int(row["release_year"])
    if row.get("rating_count") is not None:
        row["rating_count"] = int(row["rating_count"])

    return row


def run(limit: int | None = None, reset: bool = False) -> dict:
    """Do the whole import. Returns a stats dict for the report."""
    cfg = load_config()
    dataset = cfg["dataset"]

    csv_path = (REPO_ROOT / dataset["csv_path"]).resolve()
    if not csv_path.exists():
        raise SystemExit(
            f"Could not find the dataset at {csv_path}\n\n"
            "It is gitignored on purpose (447 MB), so each of us downloads it.\n"
            "Get it from:\n"
            "  https://www.kaggle.com/datasets/artermiloff/steam-games-dataset\n"
            "and save it to that path, or point dataset.csv_path somewhere else."
        )

    print(f"Reading {csv_path.name} ...")
    chosen, stats = select_games(cfg, csv_path, limit)

    print("Hashing the source file (this takes a few seconds) ...")
    stats["dataset_hash"] = sha256_file(csv_path)
    # Record the path relative to the repo, like "data/raw/games.csv", rather
    # than the full path on whoever's laptop ran the import. The report is
    # committed, so an absolute path would just show one person's folders.
    try:
        stats["dataset_snapshot_ref"] = csv_path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        stats["dataset_snapshot_ref"] = str(csv_path)   # CSV kept outside the repo

    aliases = alias_lookup(cfg)
    registry = FeatureRegistry(cfg)

    source_name = dataset["source_name"]
    retrieved_at = str(dataset.get("retrieved_at") or "")

    # Everything below happens inside one transaction. If anything raises,
    # the whole import rolls back and the database is left exactly as it was.
    # There is no such thing as a half-finished import.
    with SessionLocal() as session, session.begin():

        # Safety check: re-importing games while published maps exist would
        # leave those maps pointing at games that may have changed underneath
        # them. Better to stop and make someone think about it.
        if session.scalar(select(func.count()).select_from(MapVersion)):
            raise SystemExit(
                "There are already published map versions in this database.\n"
                "Re-importing games now could break them, so this is blocked.\n"
                "Clear map_versions first if you really mean to do this."
            )

        # Remember which game_id we gave each Steam app id last time, so a
        # rebuild does not renumber everything.
        existing_ids = dict(
            session.execute(
                select(GameSource.external_id, GameSource.game_id).where(
                    GameSource.source_name == source_name
                )
            ).all()
        )
        next_id = (session.scalar(select(func.max(Game.game_id))) or 0) + 1

        if reset and existing_ids:
            # Delete children before parents, or the foreign keys complain.
            session.execute(delete(GameFeatureCoverage))
            session.execute(delete(GameFeature))
            session.execute(delete(GameSource))
            session.execute(delete(Game))
            session.execute(delete(Feature))
            session.flush()
        elif existing_ids:
            raise SystemExit(
                "This database already has an import in it.\n"
                "Run with --reset to wipe and rebuild."
            )

        # --- writing, in batches -------------------------------------------
        #
        # We flush games, sources and coverage to the database every BATCH_SIZE
        # rows instead of building one giant list first. That matters a lot at
        # full-catalogue size: 90,000 long descriptions held in memory at once
        # is a few gigabytes, and the machine running this may not have it.
        #
        # Feature LINKS cannot be written yet, because a feature needs an id
        # and we do not know the full list of features until every game has
        # been read. So we collect those as lightweight (game_id, key) pairs,
        # which are small, and write them after the loop.
        BATCH_SIZE = 2000

        game_rows: list[dict] = []
        source_rows: list[dict] = []
        coverage_rows: list[dict] = []
        pending_links: list[tuple[int, tuple[str, str]]] = []
        unmapped_tags: dict[str, int] = {}
        total_written = 0

        def flush_batch():
            """Write whatever is buffered, then empty the buffers."""
            nonlocal total_written
            if game_rows:
                session.execute(Game.__table__.insert(), game_rows)
                session.execute(GameSource.__table__.insert(), source_rows)
                session.execute(GameFeatureCoverage.__table__.insert(), coverage_rows)
                total_written += len(game_rows)
                game_rows.clear()
                source_rows.clear()
                coverage_rows.clear()

        for tuple_row in chosen.itertuples(index=False):
            raw = {column: getattr(tuple_row, column) for column in chosen.columns}

            appid = str(int(raw["appid"]))
            game_id = existing_ids.get(appid)
            if game_id is None:
                game_id = next_id
                next_id += 1

            game_rows.append(build_game_row(raw, cfg, game_id))

            source_rows.append({
                "source_name": source_name,
                "external_id": appid,
                "game_id": game_id,
                "source_url": dataset["store_url_template"].format(appid=appid),
                "retrieved_at": retrieved_at,
            })

            features, coverage = resolve_features(raw, cfg, aliases, registry)
            for key in features:
                pending_links.append((game_id, key))
            for category, status in coverage.items():
                coverage_rows.append({
                    "game_id": game_id,
                    "category": category,
                    "status": status,
                })

            # Track tags with no alias, so the report can tell Austin and
            # Kayne which ones are worth mapping next.
            for raw_tag in raw["tag_list"]:
                if map_raw_tag(raw_tag, aliases)[0] == "tag":
                    unmapped_tags[raw_tag] = unmapped_tags.get(raw_tag, 0) + 1

            if len(game_rows) >= BATCH_SIZE:
                flush_batch()
                if total_written % 20000 == 0:
                    print(f"  ... {total_written:,} games written")

        flush_batch()   # whatever is left over

        # Now that every game has been read, we know the full set of features.
        # Give each one an id, sorted so the ids come out the same on every
        # machine, which keeps REL 2 honest.
        feature_ids: dict[tuple[str, str], int] = {}
        feature_rows = []
        for index, ((category, name), display) in enumerate(sorted(registry.rows.items()), start=1):
            feature_ids[(category, name)] = index
            feature_rows.append({
                "feature_id": index,
                "category": category,
                "name": name,
                "display_name": display,
            })

        session.execute(Feature.__table__.insert(), feature_rows)

        # Write the links in chunks too. At full-catalogue size this is about
        # two million rows, and handing SQLite one parameter list that long is
        # asking for trouble.
        link_count = len(pending_links)
        for start in range(0, link_count, 10000):
            session.execute(
                GameFeature.__table__.insert(),
                [
                    {"game_id": gid, "feature_id": feature_ids[key]}
                    for gid, key in pending_links[start:start + 10000]
                ],
            )

    stats["features_created"] = len(feature_rows)
    stats["game_feature_pairs"] = link_count
    stats["unmapped_tags"] = unmapped_tags
    stats["column_sources"] = cfg["fields"]["column_sources"]
    stats["config_snapshot_json"] = json.dumps(cfg, ensure_ascii=False, default=str)
    return stats


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description="Import games from the Steam CSV into our database."
    )
    parser.add_argument("--limit", type=int, default=None,
                        help="import this many games instead of the config's target_count")
    parser.add_argument("--reset", action="store_true",
                        help="wipe the existing import and rebuild from scratch")
    args = parser.parse_args(argv)

    stats = run(limit=args.limit, reset=args.reset)

    # Imported here rather than at the top so the report module is only
    # loaded when we actually need it.
    from pipeline.report import print_report

    print_report(stats)


if __name__ == "__main__":
    sys.exit(main())
