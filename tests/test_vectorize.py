"""Behaviour of the tag vectorization methods (REL 2, MAINT 2)."""
import dataclasses

import numpy as np
import pytest

from backend.app.db import DB_PATH
from pipeline.config import load_config
from pipeline.vectorize import (
    EMBEDDING_METHODS,
    METHODS,
    TagCorpus,
    load_corpus,
    vectorize,
)

CORE_METHODS = [m for m in METHODS if m not in EMBEDDING_METHODS]

PARAMS = {
    "description_floor": 0.4,
    "hybrid_alpha": 0.7,
    "rank_depth": 5,
    "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
    "embedding_revision": "1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
    "embedding_tag_template": "a video game tagged {tag}",
}


@pytest.fixture
def corpus() -> TagCorpus:
    # tags: action, puzzle, rpg, shooter, space. "action" is on every game.
    return TagCorpus(
        game_ids=np.array([1, 2, 3, 4]),
        titles=["A", "B", "C", "D"],
        tags=["action", "puzzle", "rpg", "shooter", "space"],
        votes=np.array(
            [
                [100.0, 0, 0, 50, 10],
                [80.0, 40, 0, 0, 5],
                [300.0, 0, 90, 0, 0],
                [20.0, 0, 0, 20, 0],
            ]
        ),
        descriptions=[
            "A frantic shooter set in deep space.",
            "Solve every puzzle on the station.",
            "A sprawling adventure about a lone knight.",
            "Quiet moments between rounds.",
        ],
    )


@pytest.mark.parametrize("method", CORE_METHODS)
def test_rows_are_unit_norm(corpus, method):
    norms = np.linalg.norm(vectorize(corpus, method, PARAMS), axis=1)
    np.testing.assert_allclose(norms, 1.0)


@pytest.mark.parametrize("method", CORE_METHODS)
def test_weight_is_zero_exactly_where_tag_is_absent(corpus, method):
    vectors = vectorize(corpus, method, PARAMS)
    assert np.all(vectors[~corpus.present] == 0)
    assert np.all(vectors[corpus.present] > 0)


@pytest.mark.parametrize("method", CORE_METHODS)
def test_deterministic(corpus, method):
    first = vectorize(corpus, method, PARAMS)
    second = vectorize(corpus, method, PARAMS)
    np.testing.assert_array_equal(first, second)


def test_binary_row_is_presence_over_sqrt_k(corpus):
    row = vectorize(corpus, "binary", PARAMS)[0]
    np.testing.assert_allclose(row, corpus.present[0] / np.sqrt(3))


@pytest.mark.parametrize("method", ["votes_max", "votes_log", "votes_rank"])
def test_more_votes_within_a_game_means_more_weight(corpus, method):
    row = vectorize(corpus, method, PARAMS)[0]
    action, shooter, space = row[0], row[3], row[4]
    assert action > shooter > space


def _scale_first_game(corpus: TagCorpus, factor: float) -> TagCorpus:
    votes = corpus.votes.copy()
    votes[0] *= factor
    return dataclasses.replace(corpus, votes=votes)


@pytest.mark.parametrize(
    "method", ["votes_max", "votes_rank", "votes_max_idf", "votes_rank_idf"]
)
def test_scaling_one_games_votes_leaves_its_vector_unchanged(corpus, method):
    scaled = _scale_first_game(corpus, 100)
    np.testing.assert_allclose(
        vectorize(scaled, method, PARAMS)[0], vectorize(corpus, method, PARAMS)[0]
    )


def test_log_votes_keep_their_order_when_a_games_votes_are_scaled(corpus):
    scaled = _scale_first_game(corpus, 100)
    before = vectorize(corpus, "votes_log", PARAMS)[0]
    after = vectorize(scaled, "votes_log", PARAMS)[0]
    np.testing.assert_array_equal(np.argsort(before), np.argsort(after))
    assert np.abs(after - before).max() < 0.3  # popularity cannot reshape it much


@pytest.mark.parametrize("method", ["binary_idf", "votes_max_idf", "votes_log_idf"])
def test_tag_every_game_has_is_downweighted_against_a_rare_tag(corpus, method):
    plain = method.removesuffix("_idf")
    # Game 1 holds the ubiquitous "action" and the rare "space" at equal weight.
    votes = corpus.votes.copy()
    votes[0, 4] = votes[0, 0]
    equal = dataclasses.replace(corpus, votes=votes)
    before = vectorize(equal, plain, PARAMS)[0]
    after = vectorize(equal, method, PARAMS)[0]
    assert before[0] == pytest.approx(before[4])
    assert after[4] > after[0]


def test_unknown_method_lists_valid_names(corpus):
    with pytest.raises(ValueError) as err:
        vectorize(corpus, "nonsense", PARAMS)
    message = str(err.value)
    assert "nonsense" in message
    assert all(name in message for name in METHODS)


@pytest.mark.parametrize("method", ["desc_tfidf", "hybrid_tfidf"])
def test_tag_named_in_the_description_outranks_one_that_is_not(corpus, method):
    # Game 1 mentions "shooter" and "space"; its "action" tag has more votes
    # but is never mentioned. Equalise votes so only the description differs.
    votes = corpus.votes.copy()
    votes[0, [0, 3, 4]] = 10
    equal = dataclasses.replace(corpus, votes=votes)
    row = vectorize(equal, method, PARAMS)[0]
    assert row[3] > row[0]
    assert row[4] > row[0]


def test_description_floor_keeps_unmentioned_tags_nonzero(corpus):
    row = vectorize(corpus, "desc_tfidf", {**PARAMS, "description_floor": 0.4})[3]
    assert row[0] > 0 and row[3] > 0  # game 4's description names neither


def test_desc_embed_prefers_the_tag_the_description_is_about(corpus, tmp_path):
    pytest.importorskip("sentence_transformers")
    votes = corpus.votes.copy()
    votes[1, [0, 1, 4]] = 10  # game 2: action, puzzle, space at equal votes
    equal = dataclasses.replace(corpus, votes=votes)
    params = {**PARAMS, "embedding_cache_dir": tmp_path}
    row = vectorize(equal, "desc_embed", params)[1]
    assert row[1] > row[0]  # "Solve every puzzle" -> puzzle over action
    np.testing.assert_array_equal(row, vectorize(equal, "desc_embed", params)[1])


def test_votes_rank_breaks_vote_ties_by_steam_order(corpus):
    # Equal votes on three tags; Steam listed shooter first, then action, then space.
    votes = corpus.votes.copy()
    votes[0, [0, 3, 4]] = 10
    order = np.zeros_like(votes)
    order[0, [3, 0, 4]] = [1, 2, 3]
    tied = dataclasses.replace(corpus, votes=votes, order=order)
    action, shooter, space = vectorize(tied, "votes_rank", PARAMS)[0][[0, 3, 4]]
    assert shooter > action > space


def test_blank_description_gives_every_tag_the_floor_weight(corpus):
    blank = dataclasses.replace(corpus, descriptions=["", *corpus.descriptions[1:]])
    row = vectorize(blank, "desc_tfidf", PARAMS)[0]
    np.testing.assert_allclose(row[corpus.present[0]], 1 / np.sqrt(3))


def test_description_methods_use_the_full_zero_to_one_scale(corpus):
    weights = METHODS["desc_tfidf"](corpus, PARAMS)
    # Game 1 names shooter and space, so its best tag reaches 1.0 and its worst the floor.
    top = weights[0][corpus.present[0]]
    assert top.max() == pytest.approx(1.0)
    assert top.min() == pytest.approx(PARAMS["description_floor"])


@pytest.mark.skipif(not DB_PATH.exists(), reason="run `python -m pipeline.ingest` first")
def test_real_database_smoke():
    corpus = load_corpus()
    n_games, n_tags = corpus.votes.shape
    assert n_games > 0 and n_tags > 0
    assert len(corpus.titles) == len(corpus.descriptions) == n_games
    assert list(corpus.tags) == sorted(corpus.tags)
    params = load_config()["vectorization"]
    for method in CORE_METHODS:
        vectors = vectorize(corpus, method, params)
        assert vectors.shape == (n_games, n_tags)
        np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), 1.0)
        assert np.all(vectors[~corpus.present] == 0)


def test_load_corpus_does_not_create_a_missing_database(tmp_path):
    missing = tmp_path / "nope.db"
    with pytest.raises(Exception):
        load_corpus(missing)
    assert not missing.exists()
