"""
Tests for pipeline/add_columns.py, the tool that adds games columns without
re-importing.

It writes to the shared database while a map may be published, so these tests
check the promises it makes: it only adds what is missing, it only fills the
new columns, it never touches existing values, and it refuses to run against
a CSV that does not match the database.

Everything here uses a temporary database and a tiny made-up CSV, so it runs
in a fraction of a second and needs no download.
"""
import sqlite3

import pandas as pd
import pytest
from sqlalchemy import create_engine

import pipeline.add_columns as add_columns
from backend.app.models import Base
from pipeline.config import csv_columns_needed, load_config

NEW_COLUMNS = ["release_date", "long_description", "developers", "publishers"]


def _csv_row(appid, name, **overrides):
    """One CSV row with every column the importer reads, filled with sensible values."""
    row = {column: None for column in csv_columns_needed(load_config())}
    row.update({
        "appid": appid,
        "name": name,
        "release_date": "2020-05-17",
        "short_description": "A short blurb.",
        "about_the_game": "A much longer description of the game.",
        "detailed_description": "Store copy.",
        "developers": "['Studio A', 'Studio B']",
        "publishers": "['Publisher A']",
        "header_image": "https://example.com/h.jpg",
        "genres": "['Action']",
        "categories": "['Single-player']",
        "tags": "{'Action': 10, 'Indie': 5, 'Casual': 2}",
        "windows": True, "mac": False, "linux": False,
        "average_playtime_forever": 120,
        "pct_pos_total": 90,
        "num_reviews_total": 1000,
    })
    row.update(overrides)
    return row


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """A database in the OLD shape (no new columns) with two games, plus a CSV."""
    db_path = tmp_path / "games.db"
    Base.metadata.create_all(create_engine(f"sqlite:///{db_path}"))

    conn = sqlite3.connect(db_path)
    for column in NEW_COLUMNS:                    # make it look like main before this change
        conn.execute(f"ALTER TABLE games DROP COLUMN {column}")
    conn.executemany(
        "INSERT INTO games (game_id, title, title_search, description, popularity) "
        "VALUES (?, ?, ?, ?, ?)",
        [(1, "Game One", "game one", "kept as is", 5.0),
         (2, "Game Two", "game two", "also kept", 7.0)],
    )
    cfg = load_config()
    source = cfg["dataset"]["source_name"]
    conn.executemany(
        "INSERT INTO game_sources (source_name, external_id, game_id) VALUES (?, ?, ?)",
        [(source, "100", 1), (source, "200", 2)],
    )
    conn.commit()
    conn.close()

    csv_path = tmp_path / "games.csv"
    pd.DataFrame([_csv_row(100, "Game One"), _csv_row(200, "Game Two")]).to_csv(
        csv_path, index=False
    )
    cfg["dataset"]["csv_path"] = str(csv_path)   # absolute, so REPO_ROOT / it == it

    monkeypatch.setattr(add_columns, "DB_PATH", db_path)
    monkeypatch.setattr(add_columns, "load_config", lambda: cfg)
    return db_path, csv_path


def _columns(db_path):
    with sqlite3.connect(db_path) as conn:
        return [row[1] for row in conn.execute("PRAGMA table_info(games)")]


def test_adds_and_fills_only_the_missing_columns(setup):
    db_path, _ = setup
    result = add_columns.run()
    assert result["added"] == NEW_COLUMNS

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT release_date, long_description, developers, publishers "
            "FROM games WHERE game_id = 1"
        ).fetchone()
    assert row == ("2020-05-17", "A much longer description of the game.",
                   "Studio A, Studio B", "Publisher A")


def test_never_changes_existing_values(setup):
    """The CSV says 'A short blurb.' but the database says 'kept as is'.
    The tool must leave the database's value alone."""
    db_path, _ = setup
    add_columns.run()
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT game_id, title, description, popularity FROM games ORDER BY game_id"
        ).fetchall()
    assert rows == [(1, "Game One", "kept as is", 5.0), (2, "Game Two", "also kept", 7.0)]


def test_running_twice_is_harmless(setup):
    db_path, _ = setup
    add_columns.run()
    assert add_columns.run()["added"] == []
    assert _columns(db_path).count("developers") == 1


def test_check_mode_changes_nothing(setup):
    db_path, _ = setup
    before = _columns(db_path)
    result = add_columns.run(check_only=True)
    assert result["would_add"] == NEW_COLUMNS
    assert _columns(db_path) == before


def test_refuses_a_csv_from_a_different_snapshot(setup):
    """If a title in the CSV does not match the database, stop and change nothing."""
    db_path, csv_path = setup
    pd.DataFrame([_csv_row(100, "Renamed Game"), _csv_row(200, "Game Two")]).to_csv(
        csv_path, index=False
    )
    before = _columns(db_path)
    with pytest.raises(SystemExit):
        add_columns.run()
    assert _columns(db_path) == before


def test_refuses_when_a_game_is_missing_from_the_csv(setup):
    db_path, csv_path = setup
    pd.DataFrame([_csv_row(100, "Game One")]).to_csv(csv_path, index=False)
    before = _columns(db_path)
    with pytest.raises(SystemExit):
        add_columns.run()
    assert _columns(db_path) == before
