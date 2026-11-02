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

COPIES = {
    "clusters": """
        INSERT INTO clusters (cluster_id, name, color)
        SELECT cluster_id, display_name, color FROM src.clusters
        WHERE map_version_id = :version ORDER BY cluster_id
    """,
    "games": """
        INSERT INTO games (game_id, title, x, y, cluster_id, popularity)
        SELECT g.game_id, g.title, m.x, m.y, m.cluster_id, g.popularity
        FROM src.map_games m JOIN src.games g USING (game_id)
        WHERE m.map_version_id = :version ORDER BY g.game_id
    """,
    "game_genres": """
        INSERT INTO game_genres (game_id, genre)
        SELECT DISTINCT gf.game_id, f.display_name
        FROM src.game_features gf
        JOIN src.features f USING (feature_id)
        JOIN src.map_games m ON m.game_id = gf.game_id AND m.map_version_id = :version
        WHERE f.category = 'genre'
        ORDER BY gf.game_id, f.display_name
    """,
}


def export_map_db(source_db: Path, out_path: Path) -> tuple[str, dict[str, int]]:
    """Write the active map version of `source_db` to `out_path`.

    Returns the version id and the row count of each copied table. A failure
    leaves any existing `out_path` untouched.
    """
    tmp = out_path.with_name(out_path.name + ".tmp")
    tmp.unlink(missing_ok=True)
    conn = sqlite3.connect(tmp, uri=True)
    try:
        conn.execute("ATTACH DATABASE ? AS src", (source_db.resolve().as_uri() + "?mode=ro",))
        row = conn.execute(
            "SELECT map_version_id, created_at FROM src.map_versions WHERE is_active = 1"
        ).fetchone()
        if row is None:
            raise ValueError(f"no active map version in {source_db}; publish one first")
        version, created_at = row

        conn.executescript(SCHEMA)
        conn.execute("INSERT INTO map_info VALUES (?, ?)", (version, created_at))
        counts = {
            table: conn.execute(sql, {"version": version}).rowcount
            for table, sql in COPIES.items()
        }
        conn.commit()
        conn.close()
        os.replace(tmp, out_path)
    except BaseException:
        conn.close()
        tmp.unlink(missing_ok=True)
        raise
    return version, counts


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=MAP_DB_PATH)
    args = parser.parse_args(argv)

    version, counts = export_map_db(DB_PATH, args.out)
    summary = ", ".join(f"{n} {table}" for table, n in counts.items())
    print(f"exported map version {version} to {args.out} ({summary})")


if __name__ == "__main__":
    main()
