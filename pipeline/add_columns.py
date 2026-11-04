"""
Adds new `games` columns to an existing database WITHOUT re-importing.

WHY THIS EXISTS
    The normal import (pipeline/ingest.py) refuses to run while a map is
    published, on purpose: rebuilding the games could change ids or features
    underneath the live map. That is the right rule, but it left us stuck when
    all we wanted was to add display columns (long_description, developers,
    publishers, release_date) that the map does not use at all.

    This tool is the safe way to do that. It only ever:
      1. adds columns that models.py defines but the database is missing
      2. fills those NEW columns, matching each game by its Steam app id

    It never changes a game id, never adds or removes a game, never touches
    the features tables, and never changes a value that was already there.
    So a published map, and Kayne's map fingerprint, stay exactly as they were.

HOW TO RUN IT (from the repo root, venv active, CSV in data/raw/)
    python -m pipeline.add_columns            add and fill missing columns
    python -m pipeline.add_columns --check    only report what it would do

Running it twice is harmless. The second time there is nothing missing, so it
says so and stops.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys

import pandas as pd
from sqlalchemy.dialects import sqlite as sqlite_dialect

from backend.app.db import DB_PATH
from backend.app.models import Game
from pipeline.config import REPO_ROOT, csv_columns_needed, load_config
from pipeline.ingest import as_list, build_game_row


def missing_columns(conn: sqlite3.Connection) -> list[str]:
    """Columns models.py defines for `games` that the database file lacks.

    Kept in the order models.py lists them, so the new columns land in a
    predictable order on everyone's machine.
    """
    existing = {row[1] for row in conn.execute("PRAGMA table_info(games)")}
    return [c.name for c in Game.__table__.columns if c.name not in existing]


def sqlite_type(column_name: str) -> str:
    """The SQLite type for a column, worked out from models.py.

    Reading it from the model instead of typing it here means the type can
    never drift from what create_tables.py would have made.
    """
    column = Game.__table__.columns[column_name]
    return column.type.compile(dialect=sqlite_dialect.dialect())


def run(check_only: bool = False) -> dict:
    cfg = load_config()
    csv_path = (REPO_ROOT / cfg["dataset"]["csv_path"]).resolve()

    conn = sqlite3.connect(DB_PATH)
    try:
        to_add = missing_columns(conn)
        if not to_add:
            print("Nothing to add: the database already has every column in models.py.")
            return {"added": []}

        # Every column we add has to say where its data comes from, or we would
        # be adding a column we cannot fill.
        sources = cfg["fields"]["column_sources"]
        unmapped = [c for c in to_add if c not in sources]
        if unmapped:
            raise SystemExit(
                f"These columns are in models.py but not in fields.column_sources, "
                f"so there is no way to fill them: {unmapped}"
            )

        print(f"Database: {DB_PATH}")
        print(f"Columns to add: {', '.join(to_add)}")
        if check_only:
            print("--check given, so nothing was changed.")
            return {"added": [], "would_add": to_add}

        if not csv_path.exists():
            raise SystemExit(
                f"Could not find the dataset at {csv_path}. This tool reads the "
                "same CSV the import used, to fill the new columns."
            )

        # Map Steam app id -> (our game_id, the title we stored), for every game
        # already in the database. We fill only these games and nothing else.
        stored = {
            external_id: (game_id, title)
            for external_id, game_id, title in conn.execute(
                "SELECT s.external_id, g.game_id, g.title "
                "FROM game_sources s JOIN games g USING (game_id) "
                "WHERE s.source_name = ?",
                (cfg["dataset"]["source_name"],),
            )
        }
        print(f"Games in the database: {len(stored):,}")

        print(f"Reading {csv_path.name} ...")
        df = pd.read_csv(csv_path, usecols=csv_columns_needed(cfg), low_memory=False)
        df = df[df["appid"].notna()]
        df["appid_key"] = df["appid"].astype(int).astype(str)
        df = df[df["appid_key"].isin(stored)]

        # build_game_row expects these helper columns, which select_games in
        # ingest.py normally adds. Building rows the exact same way the import
        # does is what guarantees the values match a fresh import.
        df["name"] = df["name"].astype(str).str.strip()
        df["genre_list"] = df["genres"].apply(as_list)
        df["tag_list"] = df["tags"].apply(as_list)

        updates: list[tuple] = []
        title_mismatches: list[str] = []
        for record in df.to_dict("records"):
            game_id, stored_title = stored[record["appid_key"]]
            row = build_game_row(record, cfg, game_id)

            # Safety check: if the title from the CSV does not match what we
            # stored, this is probably a different snapshot of the dataset, and
            # filling columns from it would mix two versions of the data.
            if row["title"] != stored_title:
                title_mismatches.append(f"{stored_title!r} vs {row['title']!r}")
                continue
            updates.append(tuple(row[c] for c in to_add) + (game_id,))

        found = {u[-1] for u in updates}
        not_found = len(stored) - len(found)
        if title_mismatches or not_found:
            raise SystemExit(
                "The CSV does not match the games in this database, so nothing was "
                f"changed.\n  games missing from the CSV: {not_found}\n"
                f"  title mismatches: {len(title_mismatches)} "
                f"{title_mismatches[:3]}\n"
                "Check that data/raw/ holds the same snapshot as the import report's "
                "SHA-256."
            )

        # One transaction: either every column is added and filled, or the
        # database is left exactly as it was.
        with conn:
            for column in to_add:
                conn.execute(
                    f'ALTER TABLE games ADD COLUMN "{column}" {sqlite_type(column)}'
                )
            assignments = ", ".join(f'"{c}" = ?' for c in to_add)
            conn.executemany(
                f"UPDATE games SET {assignments} WHERE game_id = ?", updates
            )

        print(f"Added and filled {len(to_add)} columns for {len(updates):,} games.")
        return {"added": to_add, "games_updated": len(updates)}
    finally:
        conn.close()


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description="Add missing games columns without re-importing or touching the map."
    )
    parser.add_argument("--check", action="store_true",
                        help="report what would be added, change nothing")
    args = parser.parse_args(argv)
    run(check_only=args.check)


if __name__ == "__main__":
    sys.exit(main())
