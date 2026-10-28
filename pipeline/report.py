"""Post-import report.

The import rules require reporting missing values, duplicate candidates and
feature-category coverage after EVERY import. This module does that, prints it,
and writes data/import_report.md so the team can review it in a PR.
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

OPTIONAL_FIELDS = [
    "release_year", "description", "cover_image_url", "store_url",
    "playtime_hours", "rating", "rating_count", "popularity",
]


def collect() -> dict:
    out: dict = {}
    with SessionLocal() as s:
        total = s.scalar(select(func.count(Game.game_id))) or 0
        out["total_games"] = total

        missing = {}
        for field in OPTIONAL_FIELDS:
            col = getattr(Game, field)
            missing[field] = s.scalar(
                select(func.count()).select_from(Game).where(col.is_(None))
            )
        out["missing"] = missing

        # Duplicate candidates: same normalised title, NOT auto-merged.
        dupes = s.execute(
            select(Game.title_search, func.count())
            .group_by(Game.title_search)
            .having(func.count() > 1)
        ).all()
        out["duplicate_groups"] = len(dupes)
        details = []
        for title_search, _n in dupes[:25]:
            titles = s.scalars(
                select(Game.title).where(Game.title_search == title_search)
            ).all()
            details.append((title_search, titles))
        out["duplicate_details"] = details

        # Feature-category coverage.
        cov = {}
        for category in VALID_CATEGORIES:
            counts = dict(
                s.execute(
                    select(GameFeatureCoverage.status, func.count())
                    .where(GameFeatureCoverage.category == category)
                    .group_by(GameFeatureCoverage.status)
                ).all()
            )
            cov[category] = {
                "present": counts.get("present", 0),
                "absent": counts.get("absent", 0),
                "unknown": counts.get("unknown", 0),
            }
        out["coverage"] = cov

        out["features_by_category"] = dict(
            s.execute(
                select(Feature.category, func.count()).group_by(Feature.category)
            ).all()
        )
        out["feature_links"] = s.scalar(select(func.count()).select_from(GameFeature)) or 0

        # DATA 1: title, release year, >=1 genre, >=3 tags (any tag-ish feature)
        genre_ids = set(
            s.scalars(select(Feature.feature_id).where(Feature.category == "genre")).all()
        )
        per_game = Counter()
        genre_count = Counter()
        for gid, fid in s.execute(select(GameFeature.game_id, GameFeature.feature_id)):
            per_game[gid] += 1
            if fid in genre_ids:
                genre_count[gid] += 1
        complete = 0
        for g in s.scalars(select(Game)):
            if (
                g.title
                and g.release_year
                and genre_count[g.game_id] >= 1
                and per_game[g.game_id] >= 3
            ):
                complete += 1
        out["data1_complete"] = complete
        out["data1_pct"] = (complete / total * 100) if total else 0.0
    return out


def render(stats: dict | None, db: dict) -> str:
    L: list[str] = ["# Import report", ""]

    if stats:
        L += [
            "## Selection",
            "",
            "| Stage | Games |",
            "|---|---|",
            f"| Rows in source file | {stats.get('rows_in_file', '?'):,} |",
            f"| After genre exclusions | {stats.get('after_genre_exclusions', '?'):,} |",
            f"| With a parsable release year | {stats.get('with_release_year', '?'):,} |",
            f"| After year filter (`{stats.get('selection_mode')}`) | {stats.get('after_year_filter', '?'):,} |",
            f"| With at least the minimum genres | {stats.get('with_min_genres', '?'):,} |",
            f"| With at least the minimum tags | {stats.get('with_min_tags', '?'):,} |",
            f"| **Eligible pool** | **{stats.get('eligible_pool', '?'):,}** |",
            f"| **Selected** | **{stats.get('selected', '?'):,}** |",
            "",
            f"Snapshot: `{stats.get('dataset_snapshot_ref', '')}`  ",
            f"SHA-256: `{stats.get('dataset_hash', '')}`",
            "",
        ]

    total = db["total_games"]
    L += [
        "## Missing values",
        "",
        "| Field | Missing | % |",
        "|---|---|---|",
    ]
    for field, n in db["missing"].items():
        pct = (n / total * 100) if total else 0
        L.append(f"| `{field}` | {n:,} | {pct:.1f}% |")
    L.append("")

    L += [
        "## Duplicate candidates",
        "",
        f"{db['duplicate_groups']} normalised titles appear more than once. "
        "These are reported for review and are **not** merged automatically.",
        "",
    ]
    if db["duplicate_details"]:
        L += ["| Normalised title | Titles |", "|---|---|"]
        for key, titles in db["duplicate_details"]:
            L.append(f"| `{key}` | {' / '.join(titles)} |")
        L.append("")

    L += [
        "## Feature-category coverage",
        "",
        "`absent` means the source supplied the field and nothing matched the "
        "current vocabulary. `unknown` means the source gave us nothing to judge on.",
        "",
        "| Category | Present | Absent | Unknown | Features defined |",
        "|---|---|---|---|---|",
    ]
    for category, c in db["coverage"].items():
        nf = db["features_by_category"].get(category, 0)
        L.append(
            f"| `{category}` | {c['present']:,} | {c['absent']:,} | {c['unknown']:,} | {nf:,} |"
        )
    L += ["", f"Total game-feature links: {db['feature_links']:,}", ""]

    L += [
        "## DATA 1 completeness",
        "",
        f"{db['data1_complete']:,} of {total:,} games "
        f"({db['data1_pct']:.1f}%) have a title, a release year, at least one "
        "genre and at least three features. Requirement is 95%.",
        "",
    ]

    if stats and stats.get("unmapped_tags"):
        top = sorted(stats["unmapped_tags"].items(), key=lambda kv: -kv[1])[:30]
        L += [
            "## Most common unmapped tags",
            "",
            "These fell through to the display-only `tag` category. Austin and "
            "Kayne: add any of these to `aliases` in `config/map_config.yaml` "
            "to turn them into weighted features, then re-run the import.",
            "",
            "| Tag | Games |",
            "|---|---|",
        ]
        for tag, n in top:
            L.append(f"| {tag} | {n:,} |")
        L.append("")

    return "\n".join(L)


def print_report(stats: dict | None = None) -> str:
    db = collect()
    text = render(stats, db)
    out_path = REPO_ROOT / "data" / "import_report.md"
    out_path.write_text(text, encoding="utf-8")
    print("\n" + text)
    print(f"\nWritten to {out_path}")
    return text


if __name__ == "__main__":
    print_report()
