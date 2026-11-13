"""Pair resolution for the vectorization comparison (DATA 2)."""
import numpy as np

from pipeline.compare_vectors import resolve_pairs
from pipeline.vectorize import TagCorpus
from tests.conftest import no_features, order_from_votes


def corpus_with_titles(titles, votes) -> TagCorpus:
    votes = np.array(votes, dtype=float)
    return TagCorpus(
        game_ids=np.arange(1, len(titles) + 1),
        titles=titles,
        tags=["a", "b"],
        votes=votes,
        order=order_from_votes(votes),
        descriptions=[""] * len(titles),
        features=no_features(len(titles)),
    )


def test_duplicate_title_resolves_to_the_listing_with_most_tag_votes():
    corpus = corpus_with_titles(
        ["Game", "Game", "Game", "Other"], [[5, 0], [90, 40], [10, 0], [1, 1]]
    )
    assert resolve_pairs(corpus, [("Game", "Other")]) == ([(1, 3)], [])


def test_duplicate_title_with_equal_votes_resolves_to_the_lowest_game_id():
    corpus = corpus_with_titles(["Game", "Other", "Game"], [[5, 5], [1, 1], [5, 5]])
    assert resolve_pairs(corpus, [("Game", "Other")]) == ([(0, 1)], [])


def test_titles_missing_from_the_corpus_are_reported():
    corpus = corpus_with_titles(["Game", "Other"], [[1, 0], [1, 0]])
    assert resolve_pairs(corpus, [("Game", "Nope"), ("Game", "Other")]) == ([(0, 1)], ["Nope"])
