"""Schema rules from the scrum doc's import and publication rules."""
import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from backend.app.models import (
    Cluster,
    Feature,
    Game,
    GameFeature,
    MapGame,
    MapNeighbor,
    MapVersion,
)
from tests.conftest import make_clusters, make_positions


def test_required_indexes_exist(factory):
    insp = inspect(factory.kw["bind"])
    games_idx = {i["name"] for i in insp.get_indexes("games")}
    gf_idx = {i["name"] for i in insp.get_indexes("game_features")}
    assert "ix_games_title_search" in games_idx
    assert "ix_game_features_feature_id" in gf_idx


def test_foreign_keys_are_enforced(factory):
    with factory() as s:
        with pytest.raises(IntegrityError):
            with s.begin():
                s.add(GameFeature(game_id=9999, feature_id=1))


def test_feature_category_must_be_approved(factory):
    with factory() as s:
        with pytest.raises(IntegrityError):
            with s.begin():
                s.add(Feature(category="vibes", name="x", display_name="X"))


def test_feature_category_name_is_unique(factory):
    with factory() as s, s.begin():
        s.add(Feature(category="genre", name="rpg", display_name="RPG"))
    with factory() as s:
        with pytest.raises(IntegrityError):
            with s.begin():
                s.add(Feature(category="genre", name="rpg", display_name="Role Playing"))


def test_only_one_active_map_version(factory):
    with factory() as s, s.begin():
        s.add(MapVersion(map_version_id="v1", status="published", is_active=1))
    with factory() as s:
        with pytest.raises(IntegrityError):
            with s.begin():
                s.add(MapVersion(map_version_id="v2", status="published", is_active=1))


def test_active_version_must_be_published(factory):
    with factory() as s:
        with pytest.raises(IntegrityError):
            with s.begin():
                s.add(MapVersion(map_version_id="v1", status="validated", is_active=1))


def test_map_game_cluster_must_belong_to_same_version(factory):
    with factory() as s, s.begin():
        s.add(MapVersion(map_version_id="v1", status="building", is_active=0))
        s.flush()
        s.add(Cluster(map_version_id="v1", cluster_id=0))
    with factory() as s:
        with pytest.raises(IntegrityError):
            with s.begin():
                # cluster 7 does not exist for v1
                s.add(MapGame(map_version_id="v1", game_id=1, x=0.0, y=0.0, cluster_id=7))


def _seed_map(s, version="v1"):
    s.add(MapVersion(map_version_id=version, status="building", is_active=0))
    s.flush()
    s.add(Cluster(map_version_id=version, cluster_id=0))
    s.flush()
    s.execute(
        MapGame.__table__.insert(),
        [{"map_version_id": version, **p} for p in make_positions([1, 2, 3])],
    )


def test_game_cannot_recommend_itself(factory):
    with factory() as s, s.begin():
        _seed_map(s)
    with factory() as s:
        with pytest.raises(IntegrityError):
            with s.begin():
                s.add(
                    MapNeighbor(
                        map_version_id="v1", game_id=1, neighbor_game_id=1, rank=1
                    )
                )


def test_neighbor_rank_is_unique_per_game(factory):
    with factory() as s, s.begin():
        _seed_map(s)
        s.add(MapNeighbor(map_version_id="v1", game_id=1, neighbor_game_id=2, rank=1))
    with factory() as s:
        with pytest.raises(IntegrityError):
            with s.begin():
                s.add(
                    MapNeighbor(
                        map_version_id="v1", game_id=1, neighbor_game_id=3, rank=1
                    )
                )


def test_neighbor_must_be_in_the_same_map_version(factory):
    with factory() as s, s.begin():
        _seed_map(s)
    with factory() as s:
        with pytest.raises(IntegrityError):
            with s.begin():
                # game 9 exists in `games` but not in map_games for v1
                s.add(
                    MapNeighbor(
                        map_version_id="v1", game_id=1, neighbor_game_id=9, rank=2
                    )
                )
