"""
Writes the import report.

Our import rules say we have to report missing values, duplicate candidates
and feature-category coverage after EVERY import. This module does that.

It prints to the terminal and also writes data/import_report.md, so the report
is committed alongside the data and shows up in the PR diff. That means anyone
reviewing a database change can see what the data actually looks like without
installing anything or running the import themselves.
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy import func, select

from backend.app.db import SessionLocal
from backend.app.models import (
    VALID_CATEGORIES,
    Feature,
    Game,
    GameFeature,
    GameFeatureCoverage,
)
from pipeline.config import REPO_ROOT

# Columns that are allowed to be NULL. We count how many are missing for each
# one, because a sudden jump is usually the first sign something broke.
OPTIONAL_FIELDS = [
    "release_date", "release_year", "description", "long_description",
    "developers", "publishers", "cover_image_url", "store_url",
    "playtime_hours", "rating", "rating_count", "popularity",
]


def collect() -> dict:
    """Query the database and gather everything the report needs."""
    out: dict = {}
    with SessionLocal() as session:
        total = session.scalar(select(func.count(Game.game_id))) or 0
        out["total_games"] = total

        # --- how many games are missing each optional field ---
        missing = {}
        for field in OPTIONAL_FIELDS:
            column = getattr(Game, field)
            missing[field] = session.scalar(
                select(func.count()).select_from(Game).where(column.is_(None))
            )
        out["missing"] = missing

        # --- how long the text fields actually are ---
        # Useful for sanity-checking the PERF 2 budget: if long_description
        # suddenly averaged 50 KB we would want to know before shipping it.
        lengths = {}
        for field in ("description", "long_description"):
            column = getattr(Game, field)
            row = session.execute(
                select(func.avg(func.length(column)), func.max(func.length(column)))
                .where(column.isnot(None))
            ).one()
            lengths[field] = {
                "avg": int(row[0]) if row[0] else 0,
                "max": int(row[1]) if row[1] else 0,
            }
        out["text_lengths"] = lengths

        # --- possible duplicates ---
        # Reported, never merged. Our scrum doc is explicit that two games can
        # legitimately share a title (remasters, regional releases), so a human
        # decides rather than the importer.
        duplicates = session.execute(
            select(Game.title_search, func.count())
            .group_by(Game.title_search)
            .having(func.count() > 1)
        ).all()
        out["duplicate_groups"] = len(duplicates)
        details = []
        for title_search, _count in duplicates[:25]:
            titles = session.scalars(
                select(Game.title).where(Game.title_search == title_search)
            ).all()
            details.append((title_search, titles))
        out["duplicate_details"] = details

        # --- feature coverage per category ---
        coverage = {}
        for category in VALID_CATEGORIES:
            counts = dict(
                session.execute(
                    select(GameFeatureCoverage.status, func.count())
                    .where(GameFeatureCoverage.category == category)
                    .group_by(GameFeatureCoverage.status)
                ).all()
            )
            coverage[category] = {
                "present": counts.get("present", 0),
                "absent": counts.get("absent", 0),
                "unknown": counts.get("unknown", 0),
            }
        out["coverage"] = coverage

        out["features_by_category"] = dict(
            session.execute(
                select(Feature.category, func.count()).group_by(Feature.category)
            ).all()
        )
        out["feature_links"] = session.scalar(
            select(func.count()).select_from(GameFeature)
        ) or 0

        # --- DATA 1: how many games are properly complete ---
        # Needs a title, a release year, at least one genre, at least three
        # features. We count features in Python rather than SQL because the
        # genre check needs the category, and one pass is simpler to read.
        genre_ids = set(
            session.scalars(
                select(Feature.feature_id).where(Feature.category == "genre")
            ).all()
        )
        features_per_game = Counter()
        genres_per_game = Counter()
        for game_id, feature_id in session.execute(
            select(GameFeature.game_id, GameFeature.feature_id)
        ):
            features_per_game[game_id] += 1
            if feature_id in genre_ids:
                genres_per_game[game_id] += 1

        complete = 0
        for game in session.scalars(select(Game)):
            if (
                game.title
                and game.release_year
                and genres_per_game[game.game_id] >= 1
                and features_per_game[game.game_id] >= 3
            ):
                complete += 1
        out["data1_complete"] = complete
        out["data1_pct"] = (complete / total * 100) if total else 0.0

    return out


def render(stats: dict | None, db: dict) -> str:
    """Turn the gathered numbers into markdown."""
    lines: list[str] = ["# Import report", ""]

    # --- where every column came from ---
    # This answers "where did this value come from?" without anyone needing
    # to read ingest.py. It is generated from the config, so it cannot drift
    # out of date the way a hand-written table would.
    if stats and stats.get("column_sources"):
        lines += [
            "## Where each column came from",
            "",
            "Generated from `fields.column_sources` in `config/map_config.yaml`, "
            "so it always matches what the import actually did.",
            "",
            "| Database column | Source CSV column | Conversion | Notes |",
            "|---|---|---|---|",
        ]
        for column, spec in stats["column_sources"].items():
            source = f"`{spec['from']}`"
            if spec.get("fallback"):
                source += f" (falls back to `{spec['fallback']}`)"
            transform = f"`{spec['transform']}`" if spec.get("transform") else "none"
            note = " ".join(str(spec.get("note", "")).split())
            lines.append(f"| `{column}` | {source} | {transform} | {note} |")
        lines += [
            "",
            "`game_id` is ours, counted from 1. The Steam app id is kept in "
            "`game_sources.external_id`.",
            "",
            "Features come from four places: the `genres` column, the "
            "`categories` column, the three platform booleans, and the `tags` "
            "object. All four end up in `game_features`.",
            "",
        ]

    # --- selection funnel ---
    if stats:
        lines += [
            "## How we got from 89,618 games to the final set",
            "",
            "| Stage | Games left |",
            "|---|---|",
            f"| Rows in the source file | {stats.get('rows_in_file', '?'):,} |",
            f"| After dropping excluded genres | {stats.get('after_genre_exclusions', '?'):,} |",
            f"| With a readable release year | {stats.get('with_release_year', '?'):,} |",
            f"| After the year filter (`{stats.get('selection_mode')}`) | {stats.get('after_year_filter', '?'):,} |",
            f"| With at least the minimum genres | {stats.get('with_min_genres', '?'):,} |",
            f"| With at least the minimum tags | {stats.get('with_min_tags', '?'):,} |",
            f"| **Eligible to pick from** | **{stats.get('eligible_pool', '?'):,}** |",
            f"| **Actually imported** | **{stats.get('selected', '?'):,}** |",
            "",
            f"Source file: `{stats.get('dataset_snapshot_ref', '')}`  ",
            f"SHA-256: `{stats.get('dataset_hash', '')}`",
            "",
            "The hash is how we prove two people imported the exact same file.",
            "",
        ]

    total = db["total_games"]

    # --- missing values ---
    lines += [
        "## Missing values",
        "",
        "How many games have nothing in each optional column.",
        "",
        "| Column | Missing | % |",
        "|---|---|---|",
    ]
    for field, count in db["missing"].items():
        pct = (count / total * 100) if total else 0
        lines.append(f"| `{field}` | {count:,} | {pct:.1f}% |")
    lines.append("")

    # --- text sizes ---
    lengths = db.get("text_lengths", {})
    if lengths:
        lines += [
            "### Description sizes",
            "",
            "| Column | Average | Longest |",
            "|---|---|---|",
        ]
        for field, size in lengths.items():
            lines.append(f"| `{field}` | {size['avg']:,} chars | {size['max']:,} chars |")
        long_avg = lengths.get("long_description", {}).get("avg", 0)
        lines += [
            "",
            f"This is why `/map` does not send `long_description`. At about "
            f"{long_avg:,} characters each, {total:,} of them would be roughly "
            f"{long_avg * total / 1_000_000:.1f} MB in one response. It loads "
            "from `/games/{id}` when someone clicks a game instead.",
            "",
        ]

    # --- duplicates ---
    lines += [
        "## Possible duplicate titles",
        "",
        f"{db['duplicate_groups']} normalised titles show up more than once. "
        "These are listed for a human to look at and are **never** merged "
        "automatically, because remasters and regional releases are legitimately "
        "different games with the same name.",
        "",
    ]
    if db["duplicate_details"]:
        lines += ["| Normalised title | Actual titles |", "|---|---|"]
        for key, titles in db["duplicate_details"]:
            lines.append(f"| `{key}` | {' / '.join(titles)} |")
        lines.append("")

    # --- coverage ---
    lines += [
        "## Feature coverage by category",
        "",
        "`present` means we found at least one feature in that category. "
        "`absent` means the source gave us the data but nothing matched our "
        "current vocabulary. `unknown` means the source gave us nothing to go on.",
        "",
        "A high `absent` count is not a bug, it means the alias list in "
        "`config/map_config.yaml` has room to grow.",
        "",
        "| Category | Present | Absent | Unknown | Features defined |",
        "|---|---|---|---|---|",
    ]
    for category, counts in db["coverage"].items():
        defined = db["features_by_category"].get(category, 0)
        lines.append(
            f"| `{category}` | {counts['present']:,} | {counts['absent']:,} "
            f"| {counts['unknown']:,} | {defined:,} |"
        )
    lines += ["", f"Total game-to-feature links: {db['feature_links']:,}", ""]

    # --- DATA 1 ---
    lines += [
        "## DATA 1 completeness",
        "",
        f"{db['data1_complete']:,} of {total:,} games ({db['data1_pct']:.1f}%) "
        "have a title, a release year, at least one genre and at least three "
        "features. Our requirement is 95%.",
        "",
    ]

    # --- unmapped tags ---
    if stats and stats.get("unmapped_tags"):
        top = sorted(stats["unmapped_tags"].items(), key=lambda kv: -kv[1])[:30]
        lines += [
            "## Most common unmapped tags",
            "",
            "These tags had no alias, so they became display-only `tag` features "
            "with weight 0.0. Nothing was lost, the ML just does not use them.",
            "",
            "**Austin and Kayne:** this is the to-do list. Add any of these to "
            "`aliases` in `config/map_config.yaml`, then re-run the import to "
            "turn them into weighted features.",
            "",
            "| Tag | Games with it |",
            "|---|---|",
        ]
        for tag, count in top:
            lines.append(f"| {tag} | {count:,} |")
        lines.append("")

    return "\n".join(lines)


def print_report(stats: dict | None = None) -> str:
    """Build the report, print it, and save it to data/import_report.md."""
    db = collect()
    text = render(stats, db)
    out_path = REPO_ROOT / "data" / "import_report.md"
    out_path.write_text(text, encoding="utf-8")
    print("\n" + text)
    print(f"\nSaved to {out_path}")
    return text


if __name__ == "__main__":
    # Lets you regenerate the report without re-importing, though the
    # selection funnel section will be missing since that only exists
    # during an actual import.
    print_report()
