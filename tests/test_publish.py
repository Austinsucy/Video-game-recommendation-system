"""Publication rules: validate a complete map before activating it, and leave
the previously published version active if a build fails."""
import pytest
from sqlalchemy import func, select

from backend.app.models import MapGame, MapVersion
from pipeline.publish import MapValidationError, mark_failed, publish_map
from tests.conftest import make_clusters, make_neighbors, make_positions

IDS = list(range(1, 16))


def publish(factory, version="v1", **over):
    kwargs = {
        "clusters": make_clusters(1),
        "positions": make_positions(IDS),
        "neighbors": make_neighbors(IDS, per_game=10),
    }
    kwargs.update(over)
    publish_map(version, session_factory=factory, **kwargs)


def active(factory):
    with factory() as s:
        return s.scalars(
            select(MapVersion.map_version_id).where(MapVersion.is_active == 1)
        ).all()


def test_publish_activates_the_version(factory):
    publish(factory)
    assert active(factory) == ["v1"]
    with factory() as s:
        v = s.get(MapVersion, "v1")
        assert v.status == "published"
        assert s.scalar(select(func.count()).select_from(MapGame)) == len(IDS)


def test_second_publish_replaces_the_active_version(factory):
    publish(factory, "v1")
    publish(factory, "v2")
    assert active(factory) == ["v2"]
    with factory() as s:
        assert s.get(MapVersion, "v1").status == "published"
        assert s.get(MapVersion, "v1").is_active == 0


@pytest.mark.parametrize(
    "bad",
    [
        {"positions": make_positions(IDS, x=float("nan"))},
        {"positions": make_positions(IDS, x=float("inf"))},
        {"positions": make_positions(IDS, cluster_id=99)},
        {"positions": []},
        {"neighbors": make_neighbors(IDS, per_game=3)},          # below 10
        {"neighbors": [{"game_id": 1, "neighbor_game_id": 1,
                        "similarity_score": 1.0, "rank": 1}]},   # self-recommend
    ],
)
def test_failed_build_leaves_previous_version_active(factory, bad):
    publish(factory, "v1")
    with pytest.raises(MapValidationError):
        publish(factory, "v2", **bad)
    assert active(factory) == ["v1"]
    with factory() as s:
        # No partial v2 was saved.
        assert s.get(MapVersion, "v2") is None
        assert s.scalar(select(func.count()).select_from(MapGame)) == len(IDS)


def test_mapped_game_must_exist_in_games(factory):
    with pytest.raises(MapValidationError):
        publish(factory, "v1", positions=make_positions([1, 2, 9999]))


def test_duplicate_game_in_map_is_rejected(factory):
    dupes = make_positions(IDS) + make_positions([IDS[0]])
    with pytest.raises(MapValidationError):
        publish(factory, "v1", positions=dupes)


def test_cap_is_enforced(factory):
    big = [
        {"game_id": i, "x": 1.0, "y": 1.0, "cluster_id": 0} for i in range(1, 1202)
    ]
    with pytest.raises(MapValidationError):
        publish(factory, "v1", positions=big, neighbors=[])


def test_mark_failed_does_not_disturb_active(factory):
    publish(factory, "v1")
    mark_failed("v2", session_factory=factory)
    assert active(factory) == ["v1"]
    with factory() as s:
        assert s.get(MapVersion, "v2").status == "failed"
