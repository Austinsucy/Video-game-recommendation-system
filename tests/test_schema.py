"""
Tests for the rules the database itself enforces.

Each test here tries to insert something that SHOULD be impossible, and passes
only if the database refuses it. That is why nearly every test is wrapped in
`pytest.raises(IntegrityError)`: we want the failure.

These matter because a constraint that is written but not working is worse
than no constraint, since everyone assumes it is protecting them.
"""
import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from backend.app.models import (
    Cluster,
    Feature,
    GameFeature,
    MapGame,
    MapNeighbor,
    MapVersion,
)
from tests.conftest import make_positions


def test_required_indexes_exist(factory):
    """Our import rules name two indexes specifically. Check they are there."""
    inspector = inspect(factory.kw["bind"])
    games_indexes = {i["name"] for i in inspector.get_indexes("games")}
    link_indexes = {i["name"] for i in inspector.get_indexes("game_features")}

    assert "ix_games_title_search" in games_indexes
    assert "ix_game_features_feature_id" in link_indexes


def test_foreign_keys_are_enforced(factory):
    """Game 9999 does not exist, so this link should be rejected.

    If this test ever fails, it almost certainly means the PRAGMA in db.py
    stopped running, and every other foreign key in the schema is doing
    nothing. Worth treating as a serious failure.
    """
    with factory() as session:
        with pytest.raises(IntegrityError):
            with session.begin():
                session.add(GameFeature(game_id=9999, feature_id=1))


def test_feature_category_must_be_approved(factory):
    """Only our nine categories are allowed. 'vibes' is not one of them."""
    with factory() as session:
        with pytest.raises(IntegrityError):
            with session.begin():
                session.add(Feature(category="vibes", name="x", display_name="X"))


def test_feature_category_name_is_unique(factory):
    """(genre, rpg) can only exist once, even with a different display name."""
    with factory() as session, session.begin():
        session.add(Feature(category="genre", name="rpg", display_name="RPG"))

    with factory() as session:
        with pytest.raises(IntegrityError):
            with session.begin():
                session.add(
                    Feature(category="genre", name="rpg", display_name="Role Playing")
                )


def test_only_one_active_map_version(factory):
    """Two live maps at once would mean the site shows one at random."""
    with factory() as session, session.begin():
        session.add(MapVersion(map_version_id="v1", status="published", is_active=1))

    with factory() as session:
        with pytest.raises(IntegrityError):
            with session.begin():
                session.add(
                    MapVersion(map_version_id="v2", status="published", is_active=1)
                )


def test_active_version_must_be_published(factory):
    """A half-built map must not be able to go live."""
    with factory() as session:
        with pytest.raises(IntegrityError):
            with session.begin():
                session.add(
                    MapVersion(map_version_id="v1", status="validated", is_active=1)
                )


def test_map_game_cluster_must_belong_to_same_version(factory):
    """A game in v1 cannot point at a cluster that v1 does not define."""
    with factory() as session, session.begin():
        session.add(MapVersion(map_version_id="v1", status="building", is_active=0))
        session.flush()   # parent row has to exist before the child
        session.add(Cluster(map_version_id="v1", cluster_id=0))

    with factory() as session:
        with pytest.raises(IntegrityError):
            with session.begin():
                session.add(
                    MapGame(map_version_id="v1", game_id=1, x=0.0, y=0.0, cluster_id=7)
                )


def _seed_map(session, version="v1"):
    """Set up a minimal valid map so neighbour tests have something to attach to."""
    session.add(MapVersion(map_version_id=version, status="building", is_active=0))
    session.flush()
    session.add(Cluster(map_version_id=version, cluster_id=0))
    session.flush()
    session.execute(
        MapGame.__table__.insert(),
        [{"map_version_id": version, **p} for p in make_positions([1, 2, 3])],
    )


def test_game_cannot_recommend_itself(factory):
    """"Games similar to Hades: Hades" would be a pointless recommendation."""
    with factory() as session, session.begin():
        _seed_map(session)

    with factory() as session:
        with pytest.raises(IntegrityError):
            with session.begin():
                session.add(
                    MapNeighbor(map_version_id="v1", game_id=1,
                                neighbor_game_id=1, rank=1)
                )


def test_neighbor_rank_is_unique_per_game(factory):
    """Two neighbours both ranked 1 would make the ordering meaningless."""
    with factory() as session, session.begin():
        _seed_map(session)
        session.add(
            MapNeighbor(map_version_id="v1", game_id=1, neighbor_game_id=2, rank=1)
        )

    with factory() as session:
        with pytest.raises(IntegrityError):
            with session.begin():
                session.add(
                    MapNeighbor(map_version_id="v1", game_id=1,
                                neighbor_game_id=3, rank=1)
                )


def test_neighbor_must_be_in_the_same_map_version(factory):
    """Game 9 exists in `games` but is not on map v1, so it cannot be a neighbour there."""
    with factory() as session, session.begin():
        _seed_map(session)

    with factory() as session:
        with pytest.raises(IntegrityError):
            with session.begin():
                session.add(
                    MapNeighbor(map_version_id="v1", game_id=1,
                                neighbor_game_id=9, rank=2)
                )
