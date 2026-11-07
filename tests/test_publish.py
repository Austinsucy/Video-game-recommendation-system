"""
Tests for publishing a map.

The most important one here is test_failed_build_leaves_previous_version_active.
That is REL 4, and it is the requirement where a bug would be most visible to
users: a broken build taking the live map down with it.
"""
import pytest
from sqlalchemy import func, select

from backend.app.models import Game, MapGame, MapVersion
from pipeline.publish import MAX_GAMES, MapValidationError, mark_failed, publish_map
from tests.conftest import N_GAMES, make_clusters, make_neighbors, make_positions

# 15 games, so every game can have 10 neighbours and still have spares.
IDS = list(range(1, 16))


def publish(factory, version="v1", **overrides):
    """Publish a valid map, with any part swapped out for a test."""
    args = {
        "clusters": make_clusters(1),
        "positions": make_positions(IDS),
        "neighbors": make_neighbors(IDS, per_game=10),
    }
    args.update(overrides)
    publish_map(version, session_factory=factory, **args)


def active(factory):
    """Which map version is currently live?"""
    with factory() as session:
        return session.scalars(
            select(MapVersion.map_version_id).where(MapVersion.is_active == 1)
        ).all()


def test_publish_activates_the_version(factory):
    publish(factory)

    assert active(factory) == ["v1"]
    with factory() as session:
        assert session.get(MapVersion, "v1").status == "published"
        assert session.scalar(select(func.count()).select_from(MapGame)) == len(IDS)


def test_second_publish_replaces_the_active_version(factory):
    """Publishing v2 makes it live and stands v1 down, but keeps v1's history."""
    publish(factory, "v1")
    publish(factory, "v2")

    assert active(factory) == ["v2"]
    with factory() as session:
        old = session.get(MapVersion, "v1")
        assert old.status == "published"   # history kept
        assert old.is_active == 0          # but no longer live


@pytest.mark.parametrize("broken_part", [
    {"positions": make_positions(IDS, x=float("nan"))},       # NaN coordinate
    {"positions": make_positions(IDS, x=float("inf"))},       # infinite coordinate
    {"positions": make_positions(IDS, cluster_id=99)},        # cluster not defined
    {"positions": []},                                        # empty map
    {"neighbors": make_neighbors(IDS, per_game=3)},           # fewer than 10
    {"neighbors": [{"game_id": 1, "neighbor_game_id": 1,      # recommends itself
                    "similarity_score": 1.0, "rank": 1}]},
])
def test_failed_build_leaves_previous_version_active(factory, broken_part):
    """REL 4. Six different ways to break a build, all handled the same way.

    In every case: v2 is rejected, v1 is still live, and nothing partial from
    v2 is left behind in the database.
    """
    publish(factory, "v1")

    with pytest.raises(MapValidationError):
        publish(factory, "v2", **broken_part)

    assert active(factory) == ["v1"]
    with factory() as session:
        assert session.get(MapVersion, "v2") is None   # no leftovers
        assert session.scalar(select(func.count()).select_from(MapGame)) == len(IDS)


def test_mapped_game_must_exist_in_games(factory):
    with pytest.raises(MapValidationError):
        publish(factory, "v1", positions=make_positions([1, 2, 9999]))


def test_duplicate_game_in_map_is_rejected(factory):
    duplicated = make_positions(IDS) + make_positions([IDS[0]])
    with pytest.raises(MapValidationError):
        publish(factory, "v1", positions=duplicated)


def seed_games(factory, ids):
    with factory() as session, session.begin():
        session.add_all(
            Game(game_id=i, title=f"Game {i}", title_search=f"game {i}") for i in ids if i > N_GAMES
        )


def test_cap_is_enforced(factory):
    """CON 3 caps us at 1100 games until performance is re-tested."""
    ids = list(range(1, MAX_GAMES + 2))
    seed_games(factory, ids)
    with pytest.raises(MapValidationError, match="cap"):
        publish(factory, "v1", positions=make_positions(ids), neighbors=[])


def test_a_raised_cap_lets_a_bigger_map_through(factory):
    """CON 3 allows more than 1,100 games once PERF 1-3 are retested; max_map_games sets the cap."""
    ids = list(range(1, MAX_GAMES + 2))
    seed_games(factory, ids)
    publish(factory, "v1", positions=make_positions(ids), neighbors=[], max_games=MAX_GAMES + 1)
    assert active(factory) == ["v1"]


def test_cannot_reuse_a_version_id(factory):
    """Overwriting a version id would destroy the history it represents."""
    publish(factory, "v1")
    with pytest.raises(MapValidationError):
        publish(factory, "v1")


def test_mark_failed_does_not_disturb_active(factory):
    publish(factory, "v1")
    mark_failed("v2", session_factory=factory)

    assert active(factory) == ["v1"]
    with factory() as session:
        assert session.get(MapVersion, "v2").status == "failed"
