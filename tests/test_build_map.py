"""Behaviour of the map builder (GM 1, REL 2)."""
import copy
import math

import numpy as np
import pytest
from sqlalchemy import select

from backend.app.db import DB_PATH
from backend.app.models import MapGame, MapVersion
from pipeline import publish
from pipeline.build_map import (
    assign_clusters,
    build_map,
    layout_2d,
    neighbors_kept_on_map,
    nearest_neighbors,
    separate_collisions,
)
from pipeline.config import alias_lookup, load_config
from pipeline.vectorize import TagCorpus, load_corpus
from tests.conftest import N_GAMES, no_features, order_from_votes

N_TAGS = 12


@pytest.fixture
def cfg() -> dict:
    cfg = copy.deepcopy(load_config())
    cfg["vectorization"]["method"] = "votes_log"
    cfg["cluster_count"] = 3
    return cfg


@pytest.fixture
def corpus() -> TagCorpus:
    """20 games in 3 loose groups. Games 5 and 6 have identical tag votes."""
    rng = np.random.default_rng(0)
    votes = np.zeros((N_GAMES, N_TAGS))
    for i in range(N_GAMES):
        group = i % 3
        own = rng.choice(np.arange(group * 4, group * 4 + 4), 3, replace=False)
        votes[i, own] = rng.integers(50, 500, size=3)
        votes[i, rng.integers(0, N_TAGS)] += rng.integers(1, 20)
    votes[5] = votes[4]
    return TagCorpus(
        game_ids=np.arange(1, N_GAMES + 1),
        titles=[f"Game {i}" for i in range(1, N_GAMES + 1)],
        tags=[f"tag{j:02d}" for j in range(N_TAGS)],
        votes=votes,
        order=order_from_votes(votes),
        descriptions=["" for _ in range(N_GAMES)],
        features=no_features(N_GAMES),
    )


def test_building_twice_gives_the_same_map(corpus, cfg):
    first, second = build_map(corpus, cfg), build_map(corpus, cfg)
    assert first.neighbors == second.neighbors
    assert first.clusters == second.clusters
    assert [p["cluster_id"] for p in first.positions] == [
        p["cluster_id"] for p in second.positions
    ]
    for a, b in zip(first.positions, second.positions):
        assert a["x"] == pytest.approx(b["x"], abs=1e-6)
        assert a["y"] == pytest.approx(b["y"], abs=1e-6)


def test_map_publishes_into_the_database(corpus, cfg, factory):
    build = build_map(corpus, cfg)
    publish.publish_map(
        "v-test",
        build.clusters,
        build.positions,
        build.neighbors,
        session_factory=factory,
    )
    with factory() as s:
        assert s.get(MapVersion, "v-test").is_active == 1
        assert len(s.scalars(select(MapGame)).all()) == N_GAMES


def test_neighbours_exclude_self_and_are_sorted_best_first(corpus, cfg):
    build = build_map(corpus, cfg)
    by_game: dict[int, list[dict]] = {}
    for n in build.neighbors:
        by_game.setdefault(n["game_id"], []).append(n)
    assert len(by_game) == N_GAMES
    for game_id, rows in by_game.items():
        assert len(rows) == cfg["layout"]["neighbor_count"]
        assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))
        assert game_id not in {r["neighbor_game_id"] for r in rows}
        scores = [r["similarity_score"] for r in rows]
        assert scores == sorted(scores, reverse=True)
        assert all(type(s) is float for s in scores)


def test_equal_similarity_is_broken_by_game_id():
    # Games 10, 20, 30 are identical, so game 40 sees them as an exact tie.
    unit = np.array([1.0, 0.0])
    vectors = np.array([unit, unit, unit, [0.0, 1.0]])
    ids = np.array([10, 20, 30, 40])
    rows = [r for r in nearest_neighbors(vectors, ids, 3) if r["game_id"] == 40]
    assert [r["neighbor_game_id"] for r in rows] == [10, 20, 30]


def test_identical_games_end_up_apart_deterministically(corpus, cfg):
    min_distance = cfg["layout"]["collision_min_distance"]
    first, second = build_map(corpus, cfg), build_map(corpus, cfg)
    assert first.collisions_moved >= 2
    pos = {p["game_id"]: (p["x"], p["y"]) for p in first.positions}
    assert math.dist(pos[5], pos[6]) >= min_distance
    assert first.positions == second.positions


def test_separate_collisions_spreads_a_stack_and_leaves_others_alone():
    coords = np.array([[0.0, 0.0]] * 4 + [[50.0, 50.0]])
    ids = np.array([4, 3, 2, 1, 9])
    out, moved = separate_collisions(coords, ids, 1.0)
    assert moved == 4
    np.testing.assert_array_equal(out[4], coords[4])
    for i in range(4):
        for j in range(i + 1, 4):
            assert math.dist(out[i], out[j]) >= 1.0
    again, _ = separate_collisions(coords, ids, 1.0)
    np.testing.assert_array_equal(out, again)


def test_separation_keeps_a_ring_away_from_a_point_just_outside_the_group():
    # Two coincident games form a ring of radius ~0.5; the third sits 1.2 from
    # the pair's centre, so it starts outside the group but lands inside the ring's reach.
    coords = np.array([[0.0, 0.0], [0.0, 0.0], [1.2, 0.0]])
    out, _ = separate_collisions(coords, np.array([1, 2, 3]), 1.0)
    for i in range(3):
        for j in range(i + 1, 3):
            assert math.dist(out[i], out[j]) >= 1.0


def test_every_game_has_exactly_one_known_cluster(corpus, cfg):
    build = build_map(corpus, cfg)
    cluster_ids = {c["cluster_id"] for c in build.clusters}
    assert len(build.positions) == N_GAMES
    assert {p["game_id"] for p in build.positions} == set(corpus.game_ids.tolist())
    assert all(p["cluster_id"] in cluster_ids for p in build.positions)
    assert sum(build.cluster_sizes) == N_GAMES
    assert all(c["display_name"] == f"Cluster {c['cluster_id']}" for c in build.clusters)
    assert len({c["color"] for c in build.clusters}) == len(build.clusters)


def test_coordinates_are_scaled_to_the_configured_extent(corpus, cfg):
    build = build_map(corpus, cfg)
    peak = max(max(abs(p["x"]), abs(p["y"])) for p in build.positions)
    assert peak == pytest.approx(cfg["layout"]["coordinate_extent"], rel=0.05)


def test_clusters_separate_groups_that_the_2d_layout_merges():
    # Groups a and b differ only along a low-variance axis that PCA drops.
    rng = np.random.default_rng(1)

    def blob(centre):
        return rng.normal(centre, 0.02, size=(10, 3))

    a, b = blob([5, 0, 0]), blob([5, 0, 0.5])
    far = [blob([-5, 4, 0]), blob([-5, -4, 0])]
    vectors = np.vstack([a, b, *far])
    labels = assign_clusters(vectors, 4, seed=42)
    assert len(set(labels[:10])) == 1 and len(set(labels[10:20])) == 1
    assert labels[0] != labels[10]

    coords = layout_2d(vectors, {"method": "pca", "coordinate_extent": 1000.0}, seed=42)
    gap_2d = np.linalg.norm(coords[:10].mean(axis=0) - coords[10:20].mean(axis=0))
    assert gap_2d < 10.0  # under 1% of the extent: the layout cannot tell them apart


@pytest.mark.skipif(not DB_PATH.exists(), reason="run `python -m pipeline.ingest` first")
def test_real_database_dry_build_validates():
    cfg = load_config()
    corpus = load_corpus(DB_PATH, alias_lookup(load_config()))
    build = build_map(corpus, cfg)
    publish.validate(
        build.clusters, build.positions, build.neighbors, set(corpus.game_ids.tolist())
    )
    assert len(build.clusters) == cfg["cluster_count"]


def test_tsne_keeps_more_true_neighbours_close_than_pca():
    rng = np.random.default_rng(0)
    centres = rng.normal(size=(8, 40))
    vectors = np.vstack([rng.normal(c, 0.3, size=(25, 40)) for c in centres])
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    kept = {
        method: neighbors_kept_on_map(
            layout_2d(vectors, {"method": method, "coordinate_extent": 1000.0, "tsne_perplexity": 30}, seed=42),
            vectors,
            10,
        )
        for method in ("pca", "tsne")
    }
    assert kept["tsne"] > kept["pca"]


def test_tsne_layout_is_reproducible():
    rng = np.random.default_rng(1)
    vectors = rng.normal(size=(60, 12))
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    layout = {"method": "tsne", "coordinate_extent": 1000.0, "tsne_perplexity": 15}
    np.testing.assert_array_equal(layout_2d(vectors, layout, seed=42), layout_2d(vectors, layout, seed=42))
