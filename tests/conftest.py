"""Shared fixtures: an in-memory database for schema and publish logic tests."""
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.models import Base, Game

N_GAMES = 20


@pytest.fixture
def factory():
    """Fresh in-memory database with foreign keys on and N_GAMES games."""
    engine = create_engine("sqlite://", poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk_on(conn, _record):
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    make = sessionmaker(engine)
    with make() as s, s.begin():
        s.add_all(
            [
                Game(game_id=i, title=f"Game {i}", title_search=f"game {i}")
                for i in range(1, N_GAMES + 1)
            ]
        )
    return make


def make_clusters(n=1):
    return [
        {"cluster_id": i, "display_name": f"C{i}", "color": "#888888", "description": ""}
        for i in range(n)
    ]


def make_positions(ids, x=1.0, cluster_id=0):
    return [
        {"game_id": gid, "x": x + gid, "y": 2.0, "cluster_id": cluster_id}
        for gid in ids
    ]


def make_neighbors(ids, per_game=10):
    """Give every game `per_game` distinct neighbours, ranked 1..per_game."""
    out = []
    ordered = list(ids)
    for gid in ordered:
        others = [o for o in ordered if o != gid][:per_game]
        for rank, other in enumerate(others, start=1):
            out.append(
                {
                    "game_id": gid,
                    "neighbor_game_id": other,
                    "similarity_score": 1.0 / rank,
                    "rank": rank,
                }
            )
    return out
