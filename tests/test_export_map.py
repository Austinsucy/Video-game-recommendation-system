import sqlite3

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.app.models import Base, Feature, Game, GameFeature
from pipeline import export_map
from pipeline.export_map import export_map_db
from pipeline.publish import publish_map
from tests.conftest import make_clusters, make_neighbors, make_positions

IDS = list(range(1, 16))


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "games.db"
    engine = create_engine(f"sqlite:///{path}")

    @event.listens_for(engine, "connect")
    def _fk_on(conn, _record):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    make = sessionmaker(engine)
    with make() as s, s.begin():
        s.add_all(
            Game(
                game_id=i, title=f"Game {i}", title_search=f"game {i}",
                popularity=i / 10, description="heavy text",
            )
            for i in IDS
        )
        s.add_all(
            [
                Feature(feature_id=1, category="genre", name="rpg", display_name="RPG"),
                Feature(feature_id=2, category="genre", name="action", display_name="Action"),
                Feature(feature_id=3, category="tag", name="cozy", display_name="Cozy"),
            ]
        )
        s.flush()
        s.add_all(
            [
                GameFeature(game_id=1, feature_id=2),
                GameFeature(game_id=1, feature_id=1),
                GameFeature(game_id=1, feature_id=3),
                GameFeature(game_id=2, feature_id=1),
            ]
        )
    return path, make


def publish(make, version, x=1.0, clusters=None):
    publish_map(
        version,
        clusters or make_clusters(2),
        make_positions(IDS, x=x),
        make_neighbors(IDS),
        session_factory=make,
    )


def rows(db, sql):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def test_exports_the_active_map(source, tmp_path):
    path, make = source
    publish(make, "v1")
    out = tmp_path / "map.db"

    assert export_map_db(path, out) == ("v1", {"clusters": 2, "games": len(IDS), "game_genres": 3})

    assert rows(out, "SELECT map_version FROM map_info") == [("v1",)]
    assert rows(out, "SELECT * FROM clusters ORDER BY cluster_id") == [
        (0, "C0", "#888888"),
        (1, "C1", "#888888"),
    ]
    games = rows(out, "SELECT * FROM games ORDER BY game_id")
    assert len(games) == len(IDS)
    assert games[2] == (3, "Game 3", 4.0, 2.0, 0, 0.3)
    assert rows(out, "SELECT * FROM game_genres ORDER BY game_id, genre") == [
        (1, "Action"),
        (1, "RPG"),
        (2, "RPG"),
    ]


def test_output_has_exactly_the_four_tables(source, tmp_path):
    path, make = source
    publish(make, "v1")
    out = tmp_path / "map.db"
    export_map_db(path, out)
    assert rows(out, "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name") == [
        ("clusters",),
        ("game_genres",),
        ("games",),
        ("map_info",),
    ]


def test_only_the_active_version_is_exported(source, tmp_path):
    path, make = source
    publish(make, "v1", x=1.0)
    publish(make, "v2", x=100.0)
    out = tmp_path / "map.db"

    assert export_map_db(path, out)[0] == "v2"
    assert rows(out, "SELECT map_version FROM map_info") == [("v2",)]
    assert rows(out, "SELECT x FROM games WHERE game_id = 1") == [(101.0,)]
    assert rows(out, "SELECT COUNT(*) FROM games") == [(len(IDS),)]


def test_no_active_version_raises_and_keeps_existing_output(source, tmp_path):
    path, _ = source
    out = tmp_path / "map.db"
    out.write_bytes(b"previous")

    with pytest.raises(ValueError, match="no active map version"):
        export_map_db(path, out)

    assert out.read_bytes() == b"previous"
    assert [p.name for p in tmp_path.iterdir() if p.name != "games.db"] == ["map.db"]


def leftovers(tmp_path):
    return sorted(p.name for p in tmp_path.iterdir() if p.name != "games.db")


def test_a_failed_write_keeps_the_previous_map(source, tmp_path):
    path, make = source
    colourless = [{**c, "color": None} for c in make_clusters(2)]
    publish(make, "v1", clusters=colourless)
    out = tmp_path / "map.db"
    out.write_bytes(b"previous")

    with pytest.raises(sqlite3.IntegrityError):
        export_map_db(path, out)

    assert out.read_bytes() == b"previous"
    assert leftovers(tmp_path) == ["map.db"]


def test_a_failed_swap_keeps_the_previous_map(source, tmp_path, monkeypatch):
    path, make = source
    publish(make, "v1")
    out = tmp_path / "map.db"
    out.write_bytes(b"previous")

    def fail(*_):
        raise OSError("disk full")

    monkeypatch.setattr(export_map.os, "replace", fail)
    with pytest.raises(OSError, match="disk full"):
        export_map_db(path, out)

    assert out.read_bytes() == b"previous"
    assert leftovers(tmp_path) == ["map.db"]
