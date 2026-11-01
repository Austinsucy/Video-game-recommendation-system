"""Behaviour of the tag vectorization methods (REL 2, MAINT 2)."""
import dataclasses
import sqlite3

import numpy as np
import pytest

from backend.app.db import DB_PATH
from pipeline.config import alias_lookup, load_config, vectorization_params
from pipeline.vectorize import (
    EMBEDDING_METHODS,
    FEATURE_METHODS,
    METHODS,
    CuratedFeatures,
    TagCorpus,
    feature_strengths,
    load_corpus,
    vectorize,
)
from tests.conftest import no_features, order_from_votes

CORE_METHODS = [
    m for m in METHODS if m not in EMBEDDING_METHODS and m not in FEATURE_METHODS
]

PARAMS = {
    "description_floor": 0.4,
    "hybrid_alpha": 0.7,
    "rank_depth": 5,
    "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
    "embedding_revision": "1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
    "embedding_tag_template": "a video game tagged {tag}",
    "category_weights": {"genre": 1.0, "theme": 1.0, "tag": 0.0},
}


@pytest.fixture
def corpus() -> TagCorpus:
    # tags: action, puzzle, rpg, shooter, space. "action" is on every game.
    votes = np.array(
        [
            [100.0, 0, 0, 50, 10],
            [80.0, 40, 0, 0, 5],
            [300.0, 0, 90, 0, 0],
            [20.0, 0, 0, 20, 0],
        ]
    )
    return TagCorpus(
        game_ids=np.array([1, 2, 3, 4]),
        titles=["A", "B", "C", "D"],
        tags=["action", "puzzle", "rpg", "shooter", "space"],
        votes=votes,
        order=order_from_votes(votes),
        descriptions=[
            "A frantic shooter set in deep space.",
            "Solve every puzzle on the station.",
            "A sprawling adventure about a lone knight.",
            "Quiet moments between rounds.",
        ],
        features=no_features(4),
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
    equal = dataclasses.replace(corpus, votes=votes, order=order_from_votes(votes))
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
    equal = dataclasses.replace(corpus, votes=votes, order=order_from_votes(votes))
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
    equal = dataclasses.replace(corpus, votes=votes, order=order_from_votes(votes))
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


def test_configured_method_is_a_known_method():
    assert load_config()["vectorization"]["method"] in METHODS


@pytest.mark.skipif(not DB_PATH.exists(), reason="run `python -m pipeline.ingest` first")
def test_real_database_smoke():
    corpus = load_corpus(DB_PATH, alias_lookup(load_config()))
    n_games, n_tags = corpus.votes.shape
    assert n_games > 0 and n_tags > 0
    assert len(corpus.titles) == len(corpus.descriptions) == n_games
    assert list(corpus.tags) == sorted(corpus.tags)
    params = vectorization_params(load_config())
    for method in CORE_METHODS:
        vectors = vectorize(corpus, method, params)
        assert vectors.shape == (n_games, n_tags)
        np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), 1.0)
        assert np.all(vectors[~corpus.present] == 0)

    vectors = vectorize(corpus, "category_weighted", params)
    strength = corpus.features.strength
    assert vectors.shape == strength.shape
    assert np.all(vectors[strength == 0] == 0)
    zero_rows = ~(strength > 0).any(axis=1)
    norms = np.linalg.norm(vectors, axis=1)
    np.testing.assert_allclose(norms[~zero_rows], 1.0)
    assert np.all(norms[zero_rows] == 0) and not np.isnan(vectors).any()


def test_load_corpus_does_not_create_a_missing_database(tmp_path):
    missing = tmp_path / "nope.db"
    with pytest.raises(sqlite3.OperationalError):
        load_corpus(missing, {})
    assert not missing.exists()


# --- category_weighted -------------------------------------------------------

# columns: genre/action, genre/rpg, genre/puzzle, theme/space, theme/fantasy,
# theme/horror, theme/war, theme/pirates
FEATURE_CATEGORIES = ("genre", "genre", "genre", "theme", "theme", "theme", "theme", "theme")
FEATURE_NAMES = ("action", "rpg", "puzzle", "space", "fantasy", "horror", "war", "pirates")


def feature_corpus(strengths) -> TagCorpus:
    strengths = np.array(strengths, dtype=float)
    n = len(strengths)
    return TagCorpus(
        game_ids=np.arange(1, n + 1),
        titles=[f"G{i}" for i in range(n)],
        tags=["x"],
        votes=np.ones((n, 1)),
        order=np.ones((n, 1)),
        descriptions=[""] * n,
        features=CuratedFeatures(strengths, FEATURE_CATEGORIES, FEATURE_NAMES),
    )


def category_share(vectors: np.ndarray, category: str) -> np.ndarray:
    block = np.array(FEATURE_CATEGORIES) == category
    return np.linalg.norm(vectors[:, block], axis=1) / np.linalg.norm(vectors, axis=1)


FEATURES = [
    [1.0, 0.0, 0.5, 1.0, 0.0, 0.0, 0.0, 0.0],
    [0.0, 1.0, 0.0, 0.3, 0.9, 0.0, 0.0, 0.0],
    [0.4, 0.0, 0.0, 0.0, 0.0, 1.0, 0.6, 0.2],
    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
]
WEIGHTS = {"genre": 1.0, "theme": 1.0}


def weighted(strengths=FEATURES, **weights) -> np.ndarray:
    params = {"category_weights": {**WEIGHTS, **weights}}
    return vectorize(feature_corpus(strengths), "category_weighted", params)


def test_category_weighted_rows_are_unit_norm_or_zero_and_deterministic():
    vectors = weighted()
    np.testing.assert_allclose(np.linalg.norm(vectors[:3], axis=1), 1.0)
    assert np.all(vectors[3] == 0) and not np.isnan(vectors).any()
    np.testing.assert_array_equal(vectors, weighted())


def test_category_weighted_is_zero_exactly_where_the_game_lacks_the_feature():
    vectors = weighted()
    assert np.all(vectors[np.array(FEATURES) == 0] == 0)
    assert np.all(vectors[np.array(FEATURES) > 0] > 0)


def test_tag_with_more_votes_gets_more_weight_within_a_game():
    # Two games share the same two themes, so IDF is equal and only strength differs.
    vectors = weighted([[0, 0, 0, 0.9, 0.3, 0, 0, 0], [0, 0, 0, 0.9, 0.3, 0, 0, 0]])
    assert vectors[0, 3] > vectors[0, 4] > 0


def test_feature_strength_follows_the_games_log_votes_and_takes_the_max_over_tags():
    keys = [("genre", "rpg"), ("tag", "cozy")]
    aliases = alias_lookup(
        {"aliases": {"RPG": ["genre", "rpg"], "Role-Playing": ["genre", "rpg"]}}
    )
    raw = [{"RPG": 100, "Cozy": 10, "Role-Playing": 40}]
    links = {(1, keys[0]), (1, keys[1])}
    strength = feature_strengths([1], raw, keys, links, aliases)
    assert strength[0, 0] == pytest.approx(1.0)  # RPG is the game's top tag
    assert strength[0, 1] == pytest.approx(np.log1p(10) / np.log1p(100))


def test_feature_without_a_matching_raw_tag_has_strength_one():
    keys = [("multiplayer", "co_op"), ("genre", "rpg"), ("genre", "indie")]
    aliases = alias_lookup({"aliases": {"RPG": ["genre", "rpg"]}})
    raw = [{"RPG": 100, "Cozy": 5}]
    links = {(1, keys[0]), (1, keys[1])}
    strength = feature_strengths([1], raw, keys, links, aliases)
    assert strength[0, 0] == 1.0     # only in Steam's categories column
    assert strength[0, 1] == 1.0     # tag-derived, top tag
    assert strength[0, 2] == 0.0     # not linked, so absent


def test_a_tag_that_is_not_linked_does_not_create_a_feature():
    keys = [("genre", "rpg")]
    aliases = alias_lookup({"aliases": {"RPG": ["genre", "rpg"]}})
    strength = feature_strengths([1], [{"RPG": 100}], keys, set(), aliases)
    assert strength[0, 0] == 0.0


def test_raising_a_category_weight_raises_its_share_and_zero_removes_it():
    base = weighted()[:3]
    heavier = weighted(genre=3.0)[:3]
    assert np.all(category_share(heavier, "genre") > category_share(base, "genre"))
    assert np.all(category_share(heavier, "theme") < category_share(base, "theme"))
    removed = weighted(genre=0.0)[:3]
    assert np.all(category_share(removed, "genre") == 0)
    np.testing.assert_allclose(np.linalg.norm(removed, axis=1), 1.0)


def test_a_category_with_many_features_does_not_outweigh_one_with_a_single_feature():
    # genre has one feature; theme has all five. Equal weights give equal block norms.
    game = [[1.0, 0, 0, 1.0, 1.0, 1.0, 1.0, 1.0]]
    vectors = weighted(game * 2)
    np.testing.assert_allclose(
        category_share(vectors, "genre"), category_share(vectors, "theme")
    )


def test_curated_features_reject_mismatched_shapes():
    with pytest.raises(ValueError):
        CuratedFeatures(np.zeros(3), (), ())
    with pytest.raises(ValueError):
        CuratedFeatures(np.zeros((2, 2)), ("genre", "genre"), ("action",))
