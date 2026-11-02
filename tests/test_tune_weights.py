"""Behaviour of the category-weight search (DATA 2, UDR 1)."""
import numpy as np

from pipeline.tune_weights import PAIR_K, WEIGHT_GRID, coordinate_search, pair_ranks, score


def unit(rows):
    v = np.array(rows, dtype=float)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def test_pair_rank_is_one_when_two_games_are_each_others_closest():
    vectors = unit([[1, 0.1], [1, 0.12], [0, 1], [0.1, 1]])
    assert pair_ranks(vectors, [(0, 1), (2, 3)]).tolist() == [1, 1]


def test_pair_rank_takes_the_worse_direction():
    # Game 1 is game 0's nearest, but game 2 is closer to game 1 than game 0 is.
    vectors = unit([[1, 0], [1, 0.5], [1, 0.6]])
    assert pair_ranks(vectors, [(0, 1)]).tolist() == [2]


def test_score_prefers_more_hits_then_better_ranks():
    assert score(np.array([1, PAIR_K + 5])) > score(np.array([PAIR_K + 1, PAIR_K + 1]))
    assert score(np.array([2, 3])) > score(np.array([5, 9]))


class FakeEvaluator:
    """Pairs hit only when genre is 2.0; ranks improve as theme approaches 0.5."""

    def ranks(self, weights, pairs):
        rank = 1 if weights["genre"] == 2.0 else PAIR_K + 1
        return np.full(len(pairs), rank + abs(weights["theme"] - 0.5))


def test_coordinate_search_finds_the_best_grid_values():
    start = {"genre": 1.0, "theme": 1.0, "tag": 0.0}
    tuned = coordinate_search(FakeEvaluator(), start, [(0, 1)], rounds=3)
    assert tuned == {"genre": 2.0, "theme": 0.5, "tag": 0.0}
    assert set(tuned.values()) <= set(WEIGHT_GRID)


def test_coordinate_search_keeps_start_when_nothing_is_better():
    class Flat:
        def ranks(self, weights, pairs):
            return np.full(len(pairs), 3.0)

    start = {"genre": 1.0, "theme": 0.8, "tag": 0.0}
    assert coordinate_search(Flat(), start, [(0, 1)], rounds=2) == start
