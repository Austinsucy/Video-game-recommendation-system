"""
Unit tests for pipeline/translate.py (map v4). Small made-up data, no
database or download needed, well under a second.
"""
import numpy as np
import scipy.sparse as sp

from pipeline.translate import (
    Translator,
    colour_from_map,
    csls_topk,
    group_targets,
    hub_scores,
    spread_out,
    unit_rows,
)

SETTINGS = {"spacing_neighbor": 3, "spacing_min": 0.5, "spacing_max": 8.0, "spread_steps": 40,
            "spread_neighbors": 8, "push": 0.5, "pull": 0.05}


def test_unit_rows_leaves_zero_rows_alone():
    out = unit_rows(np.array([[3.0, 4.0], [0.0, 0.0]]))
    assert np.allclose(out, [[0.6, 0.8], [0.0, 0.0]])


def test_translator_learns_a_simple_mapping():
    # feature 0 -> target direction A, feature 1 -> direction B
    rng = np.random.default_rng(0)
    feats = sp.csr_matrix(rng.integers(0, 2, size=(400, 2)).astype(float))
    text = np.zeros((400, 3))
    targets = unit_rows(feats.toarray() @ np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]) + 1e-6)
    model = Translator(ridge_lambda=0.1, min_feature_games=5).fit(feats, text, targets)
    pred = model.predict(sp.csr_matrix([[1.0, 0.0], [0.0, 1.0]]), np.zeros((2, 3)))
    assert pred[0].argmax() == 0 and pred[1].argmax() == 1
    assert np.allclose(np.linalg.norm(pred, axis=1), 1.0, atol=1e-5)


def test_translator_drops_rare_features_and_never_goes_negative():
    common = np.r_[np.ones(10), np.zeros(10)]          # 10 games have feature 0
    rare = np.r_[1.0, np.zeros(19)]                    # only 1 game has feature 1
    feats = sp.csr_matrix(np.column_stack([common, rare]))
    targets = unit_rows(np.random.default_rng(1).random((20, 4)))
    model = Translator(min_feature_games=5).fit(feats, np.zeros((20, 2)), targets)
    assert model.columns.tolist() == [0]
    assert (model.predict(feats, np.zeros((20, 2))) >= 0).all()


def test_translator_is_deterministic():
    rng = np.random.default_rng(2)
    feats = sp.csr_matrix(rng.integers(0, 2, size=(100, 8)).astype(float))
    text = rng.normal(size=(100, 5))
    targets = unit_rows(rng.random((100, 6)))
    a = Translator().fit(feats, text, targets).predict(feats, text)
    b = Translator().fit(feats, text, targets).predict(feats, text)
    assert np.array_equal(a, b)


def test_csls_marks_down_a_hub():
    # pool game 0 is a hub: close to every new game. Game 1 is the real match for new game 0.
    pool = unit_rows(np.array([[1.0, 1.0, 1.0], [1.0, 0.1, 0.0], [0.0, 0.0, 1.0]]))
    new = unit_rows(np.array([[1.0, 0.5, 0.5], [1.0, 1.0, 1.0], [1.0, 1.0, 1.0], [1.0, 1.0, 1.0]]))
    plain = (new @ pool.T)[0].argmax()
    hubs = hub_scores(pool, new, k=3)
    idx, cos, best = csls_topk(new, pool, np.array([10, 11, 12]), hubs, k=1)
    assert plain == 0 and idx[0, 0] == 1
    assert np.isclose(best[0], (new @ pool.T)[0].max())


def test_csls_ties_go_to_the_lower_game_id():
    pool = unit_rows(np.array([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]]))
    idx, _, _ = csls_topk(unit_rows(np.array([[1.0, 0.0]])), pool, np.array([20, 10, 30]), np.zeros(3), k=2)
    assert idx[0].tolist() == [1, 0]          # game_id 10 before game_id 20


def test_group_target_picks_the_biggest_group_not_the_middle():
    # three recommendations on an island at (100, 100), one on another island at (-100, -100)
    rec_xy = np.array([[[100, 100], [101, 100], [100, 101], [-100, -100]]], dtype=float)
    sims = np.array([[0.8, 0.8, 0.8, 0.9]])
    t = group_targets(rec_xy, sims, radius=25.0, power=4)
    assert np.linalg.norm(t[0] - [100.3, 100.3]) < 2           # not near (50, 50)


def test_spreading_keeps_points_near_their_target_and_apart():
    fixed = np.array([[x, y] for x in range(0, 20, 2) for y in range(0, 20, 2)], dtype=float)
    targets = np.full((30, 2), 10.0)                            # 30 games want the same spot
    pos = spread_out(fixed, targets, np.arange(30), SETTINGS)
    assert np.linalg.norm(pos - targets, axis=1).max() < 12
    gaps = np.linalg.norm(pos[:, None] - pos[None], axis=2) + np.eye(30) * 99
    assert gaps.min() > 0.2


def test_spreading_never_moves_fixed_points_and_is_repeatable():
    fixed = np.random.default_rng(3).uniform(-50, 50, size=(200, 2))
    before = fixed.copy()
    targets = np.random.default_rng(4).uniform(-50, 50, size=(50, 2))
    a = spread_out(fixed, targets, np.arange(100, 150), SETTINGS)
    b = spread_out(fixed, targets, np.arange(100, 150), SETTINGS)
    assert np.array_equal(fixed, before) and np.array_equal(a, b)


def test_colour_comes_from_the_surrounding_map():
    fixed = np.array([[0, 0], [1, 0], [0, 1], [50, 50], [51, 50], [50, 51]], dtype=float)
    cluster = np.array([2, 2, 2, 5, 5, 5])
    out = colour_from_map(fixed, cluster, np.array([[0.5, 0.5], [50.5, 50.5]]), k=3, n_clusters=6)
    assert out.tolist() == [2, 5]
