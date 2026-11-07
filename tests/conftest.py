"""
Shared test setup.

pytest automatically finds this file and makes anything in it available to
every test, with no imports needed.

The `factory` fixture below gives each test its own brand new in-memory
database. That matters for two reasons: tests cannot interfere with each
other, and they cannot touch data/games.db, so running the test suite can
never damage real data.
"""
import zlib

import numpy as np
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.models import Base, Game
from pipeline.vectorize import CuratedFeatures

N_GAMES = 20


@pytest.fixture
def factory():
    """A fresh empty database with 20 placeholder games in it.

    "sqlite://" with no path means in-memory: nothing is written to disk and
    it disappears when the test ends.

    StaticPool is needed because an in-memory SQLite database normally only
    exists for one connection. Without it, SQLAlchemy would open a second
    connection and find an empty database, which is a confusing failure.
    """
    engine = create_engine("sqlite://", poolclass=StaticPool)

    # Same foreign key setup as the real database, otherwise tests would pass
    # here and fail in production.
    @event.listens_for(engine, "connect")
    def _turn_on_foreign_keys(conn, _record):
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    make_session = sessionmaker(engine)

    with make_session() as session, session.begin():
        session.add_all([
            Game(game_id=i, title=f"Game {i}", title_search=f"game {i}")
            for i in range(1, N_GAMES + 1)
        ])

    return make_session


# ---------------------------------------------------------------------------
# Helpers for building valid-looking map data in tests
# ---------------------------------------------------------------------------

def make_clusters(n=1):
    return [
        {"cluster_id": i, "display_name": f"C{i}", "color": "#888888",
         "description": ""}
        for i in range(n)
    ]


def make_positions(ids, x=1.0, cluster_id=0):
    """Spread games out a bit so they are not all stacked on one point."""
    return [
        {"game_id": gid, "x": x + gid, "y": 2.0, "cluster_id": cluster_id}
        for gid in ids
    ]


def make_neighbors(ids, per_game=10):
    """Give every game `per_game` neighbours, ranked 1, 2, 3 and so on."""
    out = []
    ordered = list(ids)
    for gid in ordered:
        others = [other for other in ordered if other != gid][:per_game]
        for rank, other in enumerate(others, start=1):
            out.append({
                "game_id": gid,
                "neighbor_game_id": other,
                "similarity_score": 1.0 / rank,
                "rank": rank,
            })
    return out


# ---------------------------------------------------------------------------
# Helpers for the vectorization tests (Kayne)
# ---------------------------------------------------------------------------

def no_features(n_games: int) -> CuratedFeatures:
    """Curated features for a tag-only fixture: none."""
    return CuratedFeatures(np.zeros((n_games, 0)), (), ())


def order_from_votes(votes: np.ndarray) -> np.ndarray:
    """Steam-order ranks for a synthetic corpus: by votes, ties by column; 0 if absent."""
    by_votes = np.argsort(-votes, axis=1, kind="stable")
    ranks = np.empty(votes.shape)
    np.put_along_axis(ranks, by_votes, np.arange(1, votes.shape[1] + 1), axis=1)
    return np.where(votes > 0, ranks, 0.0)


def fake_embed(texts, params):
    """Deterministic stand-in for the sentence model: unit rows, equal texts equal rows."""
    rows = []
    for text in texts:
        v = np.random.default_rng(zlib.crc32(text.encode())).normal(size=6)
        rows.append(v / np.linalg.norm(v))
    return np.array(rows)
