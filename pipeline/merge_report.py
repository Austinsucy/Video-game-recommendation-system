"""
Writes the Steam + IGDB merge report.

pipeline/report.py still writes data/import_report.md like it always has.
This module adds the parts that only exist because of the merge, in
data/merge_report.md, plus data/match_review.csv: every IGDB / Steam pair a
person should look at, one per line, so it can be opened in Excel.

Everything in here reads the stats the import returned and the finished
database. It never changes anything.
"""
from __future__ import annotations

import csv
from collections import Counter

from sqlalchemy import text

from backend.app.db import SessionLocal
from pipeline.config import REPO_ROOT

REPORT_PATH = REPO_ROOT / "data" / "merge_report.md"
REVIEW_PATH = REPO_ROOT / "data" / "match_review.csv"


def _table(headers, rows) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for row in rows:
        out.append("| " + " | ".join(str(v).replace("|", "/") for v in row) + " |")
    return out


def _companies(values) -> str:
    return ", ".join(sorted(values)) if values else ""


def write_review_csv(stats: dict) -> int:
    """data/match_review.csv: every pair a person should check.

    That is every 'review' decision, every low-confidence merge, and every
    edition-key-only pair. For each one: both titles, both years, both
    company lists, and the description score. To settle a pair, copy its two
    ids into config/match_overrides.yaml with verdict same or different.
    """
    merge = stats["merge"]
    decisions = merge["decisions"]
    steam = merge["steam_frame"].set_index("appid")
    igdb = merge["igdb_frame"].set_index("igdb_id")
    wanted = decisions[(decisions["decision"] == "review") | decisions["low_confidence"]
                       | (decisions["method"] == "edition_key_only")]
    wanted = wanted[wanted["game_id"].notna()].sort_values("igdb_id")
    with open(REVIEW_PATH, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["why_listed", "decision", "reason", "igdb_id", "igdb_title", "igdb_year",
                         "igdb_companies", "steam_appid", "steam_title", "steam_year",
                         "steam_companies", "description_score"])
        for d in wanted.to_dict("records"):
            appid = int(d["game_id"])
            s = steam.loc[appid]
            i = igdb.loc[d["igdb_id"]]
            why = ("review" if d["decision"] == "review" else
                   "low_confidence_merge" if d["low_confidence"] else "edition_key_only")
            writer.writerow([why, d["decision"], d["reason"], d["igdb_id"], i["title"],
                             _int(i["year"]), _companies(i["companies"]), appid, s["title"],
                             _int(s["year"]), _companies(s["companies"]),
                             "" if d["score"] is None or d["score"] != d["score"] else f"{d['score']:.3f}"])
    return len(wanted)


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return ""


def collect_db() -> dict:
    """Per-source numbers from the finished database."""
    out: dict = {}
    with SessionLocal() as session:
        q = lambda sql, **kw: session.execute(text(sql), kw).all()   # noqa: E731
        out["by_source"] = q("SELECT primary_source, COUNT(*) FROM games GROUP BY 1 ORDER BY 1")
        out["by_tag_source"] = q("SELECT tag_source, COUNT(*) FROM games GROUP BY 1 ORDER BY 1")
        out["flags"] = q("SELECT primary_source, SUM(is_non_game), SUM(is_adult), SUM(is_upcoming) "
                         "FROM games GROUP BY 1 ORDER BY 1")
        out["feature_sources"] = q("SELECT source, COUNT(*) FROM game_features GROUP BY 1 ORDER BY 1")
        columns = ["release_date", "description", "long_description", "developers", "publishers",
                   "cover_image_url", "header_image_url", "store_url", "playtime_hours", "rating",
                   "rating_count", "popularity", "raw_tags_json", "raw_igdb_json", "platforms_raw"]
        missing = {}
        for col in columns:
            missing[col] = dict(q(f"SELECT primary_source, SUM({col} IS NULL) FROM games GROUP BY 1"))
        out["missing"] = missing
        out["coverage"] = q(
            "SELECT g.primary_source, c.category, "
            "SUM(c.status = 'present'), SUM(c.status = 'absent'), SUM(c.status = 'unknown') "
            "FROM game_feature_coverage c JOIN games g USING (game_id) GROUP BY 1, 2 ORDER BY 1, 2")
        # DATA 1 (title, year, 1+ genre, 3+ features), split by source and tag source.
        out["data1"] = q(
            "WITH f AS (SELECT gf.game_id, COUNT(*) AS n, "
            "  SUM(ft.category = 'genre') AS g FROM game_features gf "
            "  JOIN features ft USING (feature_id) GROUP BY gf.game_id) "
            "SELECT games.primary_source, games.tag_source, COUNT(*), "
            "  SUM(games.release_year IS NOT NULL AND COALESCE(f.g, 0) >= 1 AND COALESCE(f.n, 0) >= 3) "
            "FROM games LEFT JOIN f USING (game_id) GROUP BY 1, 2 ORDER BY 1, 2")
        out["shared_titles"] = q(
            "SELECT title_search, COUNT(*) AS n, GROUP_CONCAT(primary_source || ':' || COALESCE(release_year, '?'), ' ') "
            "FROM games GROUP BY title_search HAVING n > 1 ORDER BY n DESC, title_search LIMIT 40")
        out["shared_title_groups"] = q(
            "SELECT COUNT(*), SUM(n), SUM(mixed) FROM (SELECT COUNT(*) AS n, "
            "COUNT(DISTINCT primary_source) > 1 AS mixed FROM games GROUP BY title_search HAVING n > 1)")[0]
        out["steam_rows_per_game"] = q(
            "SELECT n, COUNT(*) FROM (SELECT game_id, COUNT(*) AS n FROM game_sources "
            "WHERE source_name = :s GROUP BY game_id) GROUP BY n ORDER BY n",
            s=_steam_source())
    return out


def _steam_source() -> str:
    from pipeline.config import load_config
    return load_config()["dataset"]["source_name"]


def render(stats: dict, db: dict, review_rows: int) -> str:
    merge = stats["merge"]
    decisions = merge["decisions"]
    fold = merge["fold"]
    steam = merge["steam_frame"].set_index("appid")
    igdb_stats = merge["igdb_stats"]
    lines = ["# Steam + IGDB merge report", "",
             "Written by `python -m pipeline.ingest --reset` on the test/steam-plus-igdb branch.",
             "The rules are in DATABASE.md and config/map_config.yaml (sources).", ""]

    lines += ["## Source files", ""]
    lines += _table(["source", "file", "SHA-256"], [
        ("steam", stats["dataset_snapshot_ref"], stats["dataset_hash"]),
        ("igdb", igdb_stats["dataset_snapshot_ref"], igdb_stats["dataset_hash"]),
    ])

    # --- funnel ---
    n_folded = sum(len(v) - 1 for v in fold.groups.values())
    counts = decisions["decision"].value_counts().to_dict()
    lines += ["", "## Funnel per source", ""]
    lines += _table(["step", "steam", "igdb"], [
        ("rows in file", f"{stats['rows_in_file']:,}", f"{igdb_stats['rows_in_file']:,}"),
        ("dropped: no usable name", "", f"{igdb_stats['dropped_no_name']:,}"),
        ("dropped: category (expanded_game)", "",
         ", ".join(f"{k} {v:,}" for k, v in igdb_stats["dropped_categories"].items())),
        ("selected / cleaned", f"{stats['selected']:,}", f"{igdb_stats['after_cleaning']:,}"),
        ("folded into another app of the same game", f"{n_folded:,}", ""),
        ("merged into a Steam game", "", f"{counts.get('merge', 0):,}"),
        ("kept separate: review (a person should look)", "", f"{counts.get('review', 0):,}"),
        ("kept separate: new game", "", f"{counts.get('new', 0):,}"),
        ("games written", f"{stats['steam_games_written']:,}", f"{stats['igdb_new_games']:,}"),
    ])
    total = stats["steam_games_written"] + stats["igdb_new_games"]
    lines += ["", f"**Total games: {total:,}.**", ""]

    # --- folds ---
    lines += ["## Steam duplicate apps folded", "",
              f"{len(fold.groups)} groups, {sum(len(v) for v in fold.groups.values())} apps. "
              "The app with the most reviews is the game; the others are extra steam rows in game_sources.", ""]
    rows = []
    for kept, members in sorted(fold.groups.items()):
        rows.append((steam.at[kept, "title"], kept, ", ".join(str(m) for m in members if m != kept)))
    lines += _table(["game", "kept app", "other apps"], rows)
    lines += ["", f"Same title but NOT folded (different date, company or description): "
              f"{len(fold.not_folded):,} groups. First 25:", ""]
    lines += _table(["title", "app ids"], [
        (steam.at[g[0], "title"], ", ".join(str(a) for a in g)) for g in fold.not_folded[:25]])

    # --- matching ---
    lines += ["", "## IGDB matching: what was decided and why", ""]
    by = decisions.groupby(["decision", "method"]).size().reset_index(name="n")
    lines += _table(["decision", "rule", "IGDB games"],
                    [(r.decision, r.method, f"{r.n:,}") for r in by.sort_values(["decision", "n"], ascending=[True, False]).itertuples()])
    low = decisions[decisions["low_confidence"]]
    lines += ["", f"Low-confidence merges (description score under the separate_below threshold): "
              f"**{len(low):,}**. All are in data/match_review.csv; first 20:", ""]
    lines += _table(["IGDB title", "year", "Steam title", "Steam year", "score"], [
        (d["title"], _int(d["year"]), steam.at[int(d["game_id"]), "title"],
         _int(steam.at[int(d["game_id"]), "year"]), f"{d['score']:.2f}")
        for d in low.sort_values("igdb_id").head(20).to_dict("records")])
    lines += ["", f"data/match_review.csv lists **{review_rows:,}** pairs (reviews, low-confidence "
              "merges and edition-key-only pairs). To settle one, add it to config/match_overrides.yaml.", ""]
    overrides = merge.get("overrides") or []
    lines += [f"Overrides applied: {len(overrides)}.", ""]

    filled = merge.get("filled_counts") or {}
    lines += ["### What IGDB filled on merged Steam games (only empty columns)", ""]
    lines += _table(["column", "games"], sorted(filled.items(), key=lambda kv: -kv[1]))

    # --- non-games ---
    non_games = merge["non_games"]
    by_src = Counter(n["source"] for n in non_games)
    lines += ["", "## Not games (is_non_game = 1, stay in the database, off the map)", "",
              f"{len(non_games):,} titles: " + ", ".join(f"{k} {v:,}" for k, v in sorted(by_src.items())) +
              ". The full list is in data/non_games.csv.", ""]
    pattern_counts = Counter(n["pattern"] for n in non_games)
    lines += _table(["pattern", "titles"], pattern_counts.most_common())
    with open(REPO_ROOT / "data" / "non_games.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["game_id", "source", "title", "pattern"])
        for n in sorted(non_games, key=lambda n: n["game_id"]):
            writer.writerow([n["game_id"], n["source"], n["title"], n["pattern"]])

    # --- rescue ---
    rescue = merge["rescue"]
    groups = Counter(r["group"] for r in rescue)
    labels = {
        "duplicate_app": "duplicate app of another Steam game (folded)",
        "non_game": "not a game, by name",
        "igdb_3_plus": "matched IGDB, 3+ IGDB tags",
        "igdb_0_to_2": "matched IGDB, 0 to 2 IGDB tags",
        "no_match_has_genres_and_text": "no IGDB match, has Steam genres and a description",
        "almost_nothing": "almost nothing to go on",
    }
    lines += ["", "## Steam games with no tags: the rescue", "",
              f"{len(rescue):,} Steam apps had no tags. Rescued games got IGDB features with "
              "source 'igdb', tag_source 'igdb' and raw_tags_kind 'presence'. raw_tags_json stays NULL: "
              "no vote counts were invented.", ""]
    rows = []
    for key, label in labels.items():
        members = sorted((r for r in rescue if r["group"] == key),
                         key=lambda r: -(r.get("reviews") or 0))[:5]
        rows.append((label, f"{groups.get(key, 0):,}",
                     "; ".join(f"{r['title']} ({int(r.get('reviews') or 0):,})" for r in members)))
    lines += _table(["group", "games", "most reviewed"], rows)
    lines += ["", f"derived_text step: {'ON' if merge.get('derived_text_games') else 'off'} "
              f"({merge.get('derived_text_games', 0):,} games got derived_text features).", ""]

    # --- per-source database numbers ---
    lines += ["## The finished database, per source", ""]
    lines += _table(["primary_source", "games"], [(a, f"{b:,}") for a, b in db["by_source"]])
    lines += [""] + _table(["tag_source", "games"], [(a, f"{b:,}") for a, b in db["by_tag_source"]])
    lines += [""] + _table(["primary_source", "is_non_game", "is_adult", "is_upcoming"],
                           [(a, f"{b:,}", f"{c:,}", f"{d:,}") for a, b, c, d in db["flags"]])
    lines += [""] + _table(["game_features.source", "rows"], [(a, f"{b:,}") for a, b in db["feature_sources"]])
    lines += [""] + _table(["steam rows per game", "games"], [(a, f"{b:,}") for a, b in db["steam_rows_per_game"]])

    lines += ["", "### DATA 1 (title, year, 1+ genre, 3+ features), split by source", ""]
    lines += _table(["primary_source", "tag_source", "games", "pass DATA 1", "%"], [
        (a, b, f"{n:,}", f"{p:,}", f"{p / n * 100:.1f}") for a, b, n, p in db["data1"]])

    lines += ["", "### Missing values per source", ""]
    sources = [a for a, _ in db["by_source"]]
    totals = dict(db["by_source"])
    lines += _table(["column"] + [f"{s} missing" for s in sources], [
        (col,) + tuple(f"{(m.get(s) or 0):,} ({(m.get(s) or 0) / totals[s] * 100:.0f}%)" for s in sources)
        for col, m in db["missing"].items()])

    lines += ["", "### Feature coverage per source", ""]
    lines += _table(["source", "category", "present", "absent", "unknown"],
                    [(a, b, f"{c:,}", f"{d:,}", f"{e:,}") for a, b, c, d, e in db["coverage"]])

    groups_n, games_n, mixed = db["shared_title_groups"]
    lines += ["", "## Titles shared by several games after the merge", "",
              f"{groups_n or 0:,} title_search values are shared by {games_n or 0:,} games; "
              f"{mixed or 0:,} of those groups mix a Steam and an IGDB game. Shared titles are "
              "allowed (remakes, unrelated games with one name); the search box should show the "
              "year and platform next to them. Largest 40:", ""]
    lines += _table(["title_search", "games", "source:year"], db["shared_titles"])

    # --- aliases ---
    lines += ["", "## Alias coverage of IGDB fields", "",
              "Share of values that reach a weighted feature. 'Indie' is demoted to a tag on "
              "purpose and left out of the share. The import refuses to run below "
              "min_alias_coverage for the gated fields.", ""]
    cov = merge["alias_coverage"]
    lines += _table(["field", "values", "demoted", "mapped", "share"], [
        (f, f"{c['values']:,}", f"{c['demoted']:,}", f"{c['mapped']:,}", f"{c['share'] * 100:.1f}%")
        for f, c in cov.items()])
    lines += ["", "### Most common unmapped IGDB values (Austin's to-do list)", ""]
    for field, c in cov.items():
        lines += [f"- **{field}**: " + ", ".join(f"{v} ({n:,})" for v, n in c["top_unmapped"][:20])]
    return "\n".join(lines) + "\n"


def write_merge_report(stats: dict) -> str:
    review_rows = write_review_csv(stats)
    db = collect_db()
    report = render(stats, db, review_rows)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"\nMerge report written to {REPORT_PATH.relative_to(REPO_ROOT)}")
    print(f"Pairs to review written to {REVIEW_PATH.relative_to(REPO_ROOT)} ({review_rows:,} rows)")
    return report

