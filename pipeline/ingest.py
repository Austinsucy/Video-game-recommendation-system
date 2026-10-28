"""Import process: Steam CSV snapshot -> games, game_sources, game_features.

Everything that decides WHICH games and WHICH features lives in
config/map_config.yaml. This file only implements the mechanism.

Run from the repo root:
    python -m pipeline.ingest
    python -m pipeline.ingest --reset        # rebuild, preserving game_ids
    python -m pipeline.ingest --limit 40     # override selection.target_count
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
from pipeline.config import REPO_ROOT, alias_lookup, load_config

CSV_COLUMNS = [
    "appid", "name", "release_date", "short_description", "header_image",
    "windows", "mac", "linux", "genres", "categories", "tags",
    "metacritic_score", "user_score", "average_playtime_forever",
    "pct_pos_total", "num_reviews_total", "positive", "negative", "peak_ccu",
    "estimated_owners", "recommendations",
]

# Categories derived from Steam tags rather than a dedicated source column.
TAG_DERIVED = ("gameplay", "mechanic", "structure", "theme", "perspective")


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def slugify(value: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower())
    return s.strip("_") or "unknown"


def normalise_title(value: str) -> str:
    """title_search: lowercase, punctuation stripped, whitespace collapsed.

    Uses a Unicode-aware class so non-Latin titles survive. Stripping to
    [a-z0-9] would blank every CJK title and make them look like duplicates
    of each other.
    """
    s = re.sub(r"[^\w\s]+", " ", str(value).strip().lower(), flags=re.UNICODE)
    s = re.sub(r"_+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_cell(value):
    """Steam exports use Python literals: tags is a dict, genres a list."""
    if pd.isna(value):
        return None
    s = str(value).strip()
    if not s:
        return None
    if s[0] in "[{":
        try:
            return ast.literal_eval(s)
        except (ValueError, SyntaxError):
            return None
    return [p.strip() for p in s.split(",") if p.strip()]


def as_list(value) -> list[str]:
    parsed = parse_cell(value)
    if isinstance(parsed, dict):
        return [str(k) for k in parsed]
    if isinstance(parsed, list):
        return [str(v) for v in parsed]
    return []


def nullable_number(value, zero_is_missing: bool):
    """Steam writes 0 where it means 'no data'. Keep that out of the database."""
    n = pd.to_numeric(value, errors="coerce")
    if pd.isna(n):
        return None
    n = float(n)
    if zero_is_missing and n == 0.0:
        return None
    return n


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# selection
# ---------------------------------------------------------------------------
def select_games(cfg: dict, csv_path: Path, limit: int | None = None):
    sel = cfg["selection"]
    target = limit or sel["target_count"]

    df = pd.read_csv(csv_path, usecols=CSV_COLUMNS, low_memory=False)
    stats = {"rows_in_file": len(df)}

    df["name"] = df["name"].astype(str).str.strip()
    df = df[(df["name"] != "") & (df["name"].str.lower() != "nan")]
    df["release_year"] = pd.to_datetime(df["release_date"], errors="coerce").dt.year

    df["genre_list"] = df["genres"].apply(as_list)
    df["tag_list"] = df["tags"].apply(as_list)

    excluded = set(sel.get("exclude_genres") or [])
    demoted = set(sel.get("demote_genres_to_tags") or [])

    if excluded:
        df = df[~df["genre_list"].apply(lambda gs: bool(excluded & set(gs)))]
    stats["after_genre_exclusions"] = len(df)

    # min_genres counts only genres that will actually become genre features.
    df["real_genres"] = df["genre_list"].apply(
        lambda gs: [g for g in gs if g not in demoted]
    )

    df = df[df["release_year"].notna()]
    stats["with_release_year"] = len(df)

    mode = sel["mode"]
    if mode == "popular_pre2019":
        df = df[df["release_year"] <= sel["max_year"]]
    else:
        df = df[df["release_year"] >= sel["min_year"]]
    stats["after_year_filter"] = len(df)
    stats["selection_mode"] = mode

    df = df[df["real_genres"].str.len() >= sel["min_genres"]]
    stats["with_min_genres"] = len(df)

    df = df[df["tag_list"].str.len() >= sel["min_tags"]]
    stats["with_min_tags"] = len(df)

    rank_by = sel["rank_by"]
    df["_rank"] = pd.to_numeric(df[rank_by], errors="coerce").fillna(0)
    # Deterministic ordering (REL 2): rank descending, then title ascending.
    df = df.sort_values(["_rank", "name"], ascending=[False, True], kind="mergesort")

    stats["eligible_pool"] = len(df)
    chosen = df.head(target).copy().drop(columns=["_rank"])
    stats["selected"] = len(chosen)
    return chosen, stats


# ---------------------------------------------------------------------------
# feature resolution
# ---------------------------------------------------------------------------
class FeatureRegistry:
    """Holds the approved vocabulary and mints display-only `tag` features."""

    def __init__(self, cfg: dict):
        self.rows: dict[tuple[str, str], str] = {}
        for category, entries in cfg["vocabulary"].items():
            for entry in entries:
                self.rows[(category, entry["name"])] = entry["display_name"]
        self.approved = set(self.rows)

    def ensure_tag(self, raw: str) -> tuple[str, str]:
        key = ("tag", slugify(raw))
        if key not in self.rows:
            self.rows[key] = str(raw).strip()
        return key


def resolve_features(row, cfg: dict, aliases: dict, registry: FeatureRegistry):
    """Return (set of (category, name), coverage dict) for one game.

    A raw string that maps to a weighted category does NOT also become a `tag`
    feature. That is how "avoid counting the same concept twice" is enforced.
    """
    sel = cfg["selection"]
    demoted = set(sel.get("demote_genres_to_tags") or [])
    mp_map = sel.get("multiplayer_categories") or {}

    found: set[tuple[str, str]] = set()

    # --- genres column -----------------------------------------------------
    genres_raw = row["genre_list"]
    for raw in genres_raw:
        if raw in demoted:
            found.add(registry.ensure_tag(raw))
            continue
        hit = aliases.get(raw.strip().lower())
        if hit and hit in registry.approved:
            found.add(hit)
        else:
            found.add(registry.ensure_tag(raw))

    # --- categories column -> multiplayer ----------------------------------
    cats_raw = as_list(row["categories"])
    for raw in cats_raw:
        name = mp_map.get(raw)
        if name and ("multiplayer", name) in registry.approved:
            found.add(("multiplayer", name))

    # --- platform booleans -------------------------------------------------
    for col, name in (("windows", "windows"), ("mac", "macos"), ("linux", "linux")):
        if bool(row[col]) and ("platform", name) in registry.approved:
            found.add(("platform", name))

    # --- tags dict ---------------------------------------------------------
    tags_raw = row["tag_list"]
    for raw in tags_raw:
        hit = aliases.get(raw.strip().lower())
        if hit and hit in registry.approved:
            found.add(hit)
        else:
            found.add(registry.ensure_tag(raw))

    # --- coverage ----------------------------------------------------------
    # "absent" is relative to the CURRENT vocabulary. Expanding the vocabulary
    # in map_config.yaml means re-running the import to refresh these.
    present = {cat for cat, _ in found}
    source_seen = {
        "genre": bool(genres_raw),
        "multiplayer": bool(cats_raw),
        "platform": True,
        "tag": bool(tags_raw),
        **{c: bool(tags_raw) for c in TAG_DERIVED},
    }
    coverage = {}
    for category in VALID_CATEGORIES:
        if category in present:
            coverage[category] = "present"
        elif source_seen.get(category):
            coverage[category] = "absent"
        else:
            coverage[category] = "unknown"
    return found, coverage


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def run(limit: int | None = None, reset: bool = False) -> dict:
    cfg = load_config()
    ds = cfg["dataset"]
    flds = cfg["fields"]
    csv_path = (REPO_ROOT / ds["csv_path"]).resolve()
    if not csv_path.exists():
        raise SystemExit(
            f"Dataset not found at {csv_path}\n"
            "Download it and place it there, or change dataset.csv_path in "
            "config/map_config.yaml. The file is gitignored on purpose."
        )

    print(f"Reading {csv_path.name} ...")
    chosen, stats = select_games(cfg, csv_path, limit)
    print(f"Hashing snapshot ...")
    stats["dataset_hash"] = sha256_file(csv_path)
    stats["dataset_snapshot_ref"] = str(csv_path)

    aliases = alias_lookup(cfg)
    registry = FeatureRegistry(cfg)

    zero_missing = set(flds.get("zero_is_missing") or [])
    store_tpl = ds["store_url_template"]
    source_name = ds["source_name"]
    retrieved_at = str(ds.get("retrieved_at") or "")

    with SessionLocal() as session, session.begin():
        if session.scalar(select(func.count()).select_from(MapVersion)):
            raise SystemExit(
                "map_versions already holds rows. Re-importing games would "
                "invalidate published maps. Clear them first, deliberately."
            )

        # Preserve game_id across imports via the external Steam appid.
        existing_ids = dict(
            session.execute(
                select(GameSource.external_id, GameSource.game_id).where(
                    GameSource.source_name == source_name
                )
            ).all()
        )
        next_id = (session.scalar(select(func.max(Game.game_id))) or 0) + 1

        if reset and existing_ids:
            session.execute(delete(GameFeatureCoverage))
            session.execute(delete(GameFeature))
            session.execute(delete(GameSource))
            session.execute(delete(Game))
            session.execute(delete(Feature))
            session.flush()
        elif existing_ids:
            raise SystemExit(
                "Database already contains an import. Re-run with --reset."
            )

        games, sources, pairs, coverage_rows = [], [], [], []
        resolved: list[tuple[int, set, dict]] = []
        unmapped: dict[str, int] = {}

        for row in chosen.itertuples(index=False):
            r = {c: getattr(row, c) for c in chosen.columns}
            appid = str(int(r["appid"]))
            game_id = existing_ids.get(appid)
            if game_id is None:
                game_id = next_id
                next_id += 1

            playtime = nullable_number(
                r[flds["playtime_source"]],
                "average_playtime_forever" in zero_missing,
            )
            rating = nullable_number(r[flds["rating_source"]], False)
            rating_count = nullable_number(r[flds["rating_count_source"]], False)
            popularity = nullable_number(r[flds["popularity_source"]], False)

            raw_tags = parse_cell(r["tags"])
            desc = r["short_description"]

            games.append(
                {
                    "game_id": game_id,
                    "title": r["name"],
                    "title_search": normalise_title(r["name"]),
                    "release_year": int(r["release_year"]),
                    "description": None if pd.isna(desc) else str(desc),
                    "cover_image_url": None if pd.isna(r["header_image"]) else str(r["header_image"]),
                    "store_url": store_tpl.format(appid=appid),
                    "playtime_hours": round(playtime / 60.0, 2) if playtime else None,
                    "rating": rating,
                    "rating_scale": flds["rating_scale"] if rating is not None else None,
                    "rating_count": int(rating_count) if rating_count is not None else None,
                    "popularity": popularity,
                    "raw_tags_json": json.dumps(raw_tags, ensure_ascii=False) if raw_tags else None,
                }
            )
            sources.append(
                {
                    "source_name": source_name,
                    "external_id": appid,
                    "game_id": game_id,
                    "source_url": store_tpl.format(appid=appid),
                    "retrieved_at": retrieved_at,
                }
            )

            feats, cov = resolve_features(r, cfg, aliases, registry)
            resolved.append((game_id, feats, cov))
            for raw in r["tag_list"]:
                if raw.strip().lower() not in aliases:
                    unmapped[raw] = unmapped.get(raw, 0) + 1

        # features table: approved vocabulary + display-only tags discovered
        feature_ids: dict[tuple[str, str], int] = {}
        feature_rows = []
        for i, ((category, name), display) in enumerate(sorted(registry.rows.items()), start=1):
            feature_ids[(category, name)] = i
            feature_rows.append(
                {"feature_id": i, "category": category, "name": name, "display_name": display}
            )

        for game_id, feats, cov in resolved:
            for key in feats:
                pairs.append({"game_id": game_id, "feature_id": feature_ids[key]})
            for category, status in cov.items():
                coverage_rows.append(
                    {"game_id": game_id, "category": category, "status": status}
                )

        session.execute(Feature.__table__.insert(), feature_rows)
        session.execute(Game.__table__.insert(), games)
        session.execute(GameSource.__table__.insert(), sources)
        session.execute(GameFeature.__table__.insert(), pairs)
        session.execute(GameFeatureCoverage.__table__.insert(), coverage_rows)

    stats["features_created"] = len(feature_rows)
    stats["game_feature_pairs"] = len(pairs)
    stats["unmapped_tags"] = unmapped
    stats["config_snapshot_json"] = json.dumps(cfg, ensure_ascii=False, default=str)
    return stats


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Import games into the database.")
    ap.add_argument("--limit", type=int, default=None, help="override target_count")
    ap.add_argument("--reset", action="store_true", help="clear and rebuild")
    args = ap.parse_args(argv)

    stats = run(limit=args.limit, reset=args.reset)

    from pipeline.report import print_report

    print_report(stats)


if __name__ == "__main__":
    sys.exit(main())
