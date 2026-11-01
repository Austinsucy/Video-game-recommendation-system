"""Export the light browser database data/map.db from the published map (CON 1, GM 2).

    python -m pipeline.export_map [--out PATH]

map.db holds only what the map needs to draw: clusters, game positions and
titles, and genres. Descriptions, images, tags and neighbours stay in
data/games.db and load on click (GM 2). Only the active map version is
exported.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

from backend.app.db import DB_PATH
from pipeline.config import MAP_DB_PATH

SCHEMA = """
CREATE TABLE map_info (
    map_version TEXT PRIMARY KEY,
    created_at TEXT
);
CREATE TABLE clusters (
    cluster_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    color TEXT NOT NULL
);
CREATE TABLE games (
    game_id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    x REAL NOT NULL,
    y REAL NOT NULL,
    cluster_id INTEGER NOT NULL REFERENCES clusters,
    popularity REAL
);
CREATE TABLE game_genres (
    game_id INTEGER NOT NULL REFERENCES games,
    genre TEXT NOT NULL,
    PRIMARY KEY (game_id, genre)
);
"""

CLUSTERS_SQL = """
SELECT cluster_id, display_name, color FROM clusters
WHERE map_version_id = ? ORDER BY cluster_id
"""
GAMES_SQL = """
SELECT g.game_id, g.title, m.x, m.y, m.cluster_id, g.popularity
FROM map_games m JOIN games g USING (game_id)
WHERE m.map_version_id = ? ORDER BY g.game_id
"""
GENRES_SQL = """
SELECT gf.game_id, f.display_name
FROM game_features gf
JOIN features f USING (feature_id)
JOIN map_games m ON m.game_id = gf.game_id AND m.map_version_id = ?
WHERE f.category = 'genre'
ORDER BY gf.game_id, f.display_name
"""


def export_map_db(source_db: Path, out_path: Path) -> str:
    """Write the active map version of `source_db` to `out_path`; return the version id.

    A failure leaves any existing `out_path` untouched.
    """
    out_path = Path(out_path)
    src = sqlite3.connect(Path(source_db).resolve().as_uri() + "?mode=ro", uri=True)
    tmp = out_path.with_name(out_path.name + ".tmp")
    try:
        row = src.execute(
            "SELECT map_version_id, created_at FROM map_versions WHERE is_active = 1"
        ).fetchone()
        if row is None:
            raise ValueError(f"no active map version in {source_db}; publish one first")
        version, created_at = row

        tmp.unlink(missing_ok=True)
        dst = sqlite3.connect(tmp)
        try:
            dst.executescript(SCHEMA)
            dst.execute("INSERT INTO map_info VALUES (?, ?)", (version, created_at))
            dst.executemany(
                "INSERT INTO clusters VALUES (?, ?, ?)", src.execute(CLUSTERS_SQL, (version,))
            )
            dst.executemany(
                "INSERT INTO games VALUES (?, ?, ?, ?, ?, ?)", src.execute(GAMES_SQL, (version,))
            )
            dst.executemany(
                "INSERT INTO game_genres VALUES (?, ?)", src.execute(GENRES_SQL, (version,))
            )
            dst.commit()
        finally:
            dst.close()
        os.replace(tmp, out_path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    finally:
        src.close()
    return version


def table_counts(db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        return {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("clusters", "games", "game_genres")
        }
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=MAP_DB_PATH)
    args = parser.parse_args(argv)

    version = export_map_db(DB_PATH, args.out)
    counts = ", ".join(f"{n} {t}" for t, n in table_counts(args.out).items())
    print(f"exported map version {version} to {args.out} ({counts})")


if __name__ == "__main__":
    main()
