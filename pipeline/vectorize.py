"""Turn each game's Steam tags into a feature vector (REL 2, MAINT 2, CON 1).

Several weighting methods live side by side so they can be compared before one
is chosen for the published map (config `vectorization.method`).

Shape of the data:
    TagCorpus.votes  (n_games, n_tags)  vote count, 0 where the game lacks the tag
    method(corpus, params) -> (n_games, n_tags) non-negative weights, exactly 0
                              wherever the game lacks the tag

Steam keeps only each game's top 20 tags, so an absent tag means "not in the
top 20", never "zero votes". Every method therefore weights only present tags,
and vote counts are always normalised within the game first because they scale
with the game's popularity.

The core methods use pandas/NumPy/scikit-learn only. `desc_embed` imports
sentence-transformers lazily, so nothing else needs it installed.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = REPO_ROOT / "data" / "games.db"
ARTIFACTS_DIR = REPO_ROOT / "data" / "artifacts"

Params = Mapping[str, Any]


@dataclass(frozen=True)
class TagCorpus:
    game_ids: np.ndarray        # (n,) ordered ascending
    titles: list[str]
    tags: list[str]             # (m,) sorted
    votes: np.ndarray           # (n, m) float, 0 where the tag is absent
    descriptions: list[str]

    @property
    def present(self) -> np.ndarray:
        return self.votes > 0


def load_corpus(db_path: Path | str = DEFAULT_DB_PATH) -> TagCorpus:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT game_id, title, description, raw_tags_json "
            "FROM games ORDER BY game_id"
        ).fetchall()
    raw = [json.loads(r[3]) if r[3] else {} for r in rows]
    tags = sorted({t for tag_votes in raw for t in tag_votes})
    column = {t: j for j, t in enumerate(tags)}
    votes = np.zeros((len(rows), len(tags)))
    for i, tag_votes in enumerate(raw):
        for tag, count in tag_votes.items():
            votes[i, column[tag]] = count
    return TagCorpus(
        game_ids=np.array([r[0] for r in rows]),
        titles=[r[1] for r in rows],
        tags=tags,
        votes=votes,
        descriptions=[r[2] or "" for r in rows],
    )


# --- tag-vote methods -------------------------------------------------------

def binary(corpus: TagCorpus, params: Params) -> np.ndarray:
    return corpus.present.astype(float)


def _row_max(votes: np.ndarray) -> np.ndarray:
    return np.maximum(votes.max(axis=1, keepdims=True), 1.0)


def votes_max(corpus: TagCorpus, params: Params) -> np.ndarray:
    return corpus.votes / _row_max(corpus.votes)


def votes_log(corpus: TagCorpus, params: Params) -> np.ndarray:
    return np.log1p(corpus.votes) / np.log1p(_row_max(corpus.votes))


def votes_rank(corpus: TagCorpus, params: Params) -> np.ndarray:
    """(depth + 1 - rank) / depth: ignores vote magnitude entirely."""
    depth = params["rank_depth"]
    order = np.argsort(-corpus.votes, axis=1, kind="stable")
    ranks = np.empty_like(order)
    np.put_along_axis(ranks, order, np.arange(1, order.shape[1] + 1), axis=1)
    weights = np.clip(depth + 1 - ranks, 0, None) / depth
    return np.where(corpus.present, weights, 0.0)


def tag_idf(present: np.ndarray) -> np.ndarray:
    """Smooth IDF (sklearn's formula): a tag every game has still scores 1."""
    n = present.shape[0]
    df = present.sum(axis=0)
    return np.log((1 + n) / (1 + df)) + 1.0


def _with_idf(base: Callable[[TagCorpus, Params], np.ndarray]):
    def weighted(corpus: TagCorpus, params: Params) -> np.ndarray:
        return base(corpus, params) * tag_idf(corpus.present)

    weighted.__name__ = f"{base.__name__}_idf"
    return weighted


# --- description methods ----------------------------------------------------

def tfidf_relevance(corpus: TagCorpus) -> np.ndarray:
    """(n, m) cosine between each description and each tag name's text.

    A tag whose words never appear in any description scores 0 for every game.
    """
    vec = TfidfVectorizer(stop_words="english", sublinear_tf=True)
    desc = vec.fit_transform(corpus.descriptions)
    tag_text = vec.transform(corpus.tags)
    return (desc @ tag_text.T).toarray()


def embedding_relevance(corpus: TagCorpus, params: Params) -> np.ndarray:
    """(n, m) cosine between description and tag embeddings (cached, CPU)."""
    desc = _embed(corpus.descriptions, params)
    template = params["embedding_tag_template"]
    tags = _embed([template.format(tag=t) for t in corpus.tags], params)
    return desc @ tags.T


def _embed(texts: list[str], params: Params) -> np.ndarray:
    model_name = params["embedding_model"]
    cache_dir = Path(params.get("embedding_cache_dir", ARTIFACTS_DIR / "embeddings"))
    digest = hashlib.sha256(
        json.dumps([model_name, texts], ensure_ascii=False).encode()
    ).hexdigest()[:16]
    cache_file = cache_dir / f"{model_name.replace('/', '_')}-{digest}.npy"
    if cache_file.exists():
        return np.load(cache_file)

    from sentence_transformers import SentenceTransformer  # optional dependency

    model = SentenceTransformer(model_name, device="cpu")  # REL 2: no GPU nondeterminism
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    cache_dir.mkdir(parents=True, exist_ok=True)
    np.save(cache_file, vectors)
    return vectors


def _rescale_within_game(relevance: np.ndarray, present: np.ndarray) -> np.ndarray:
    """Min-max over each game's own tags, so only their ordering is used."""
    lo = np.where(present, relevance, np.inf).min(axis=1, keepdims=True)
    hi = np.where(present, relevance, -np.inf).max(axis=1, keepdims=True)
    span = hi - lo
    return np.where(span > 0, (relevance - lo) / np.where(span > 0, span, 1.0), 0.0)


def _description_weight(
    relevance: np.ndarray, present: np.ndarray, params: Params
) -> np.ndarray:
    """floor + (1 - floor) * relevance, on present tags only.

    The floor keeps a tag the description never mentions from vanishing: the
    tag is still in the game's top 20.
    """
    floor = params["description_floor"]
    return np.where(present, floor + (1 - floor) * relevance, 0.0)


def desc_tfidf(corpus: TagCorpus, params: Params) -> np.ndarray:
    return _description_weight(tfidf_relevance(corpus), corpus.present, params)


def desc_embed(corpus: TagCorpus, params: Params) -> np.ndarray:
    relevance = _rescale_within_game(
        embedding_relevance(corpus, params), corpus.present
    )
    return _description_weight(relevance, corpus.present, params)


def _hybrid(description_method: Callable[[TagCorpus, Params], np.ndarray]):
    def blended(corpus: TagCorpus, params: Params) -> np.ndarray:
        alpha = params["hybrid_alpha"]
        return alpha * votes_log(corpus, params) + (1 - alpha) * description_method(
            corpus, params
        )

    return blended


METHODS: dict[str, Callable[[TagCorpus, Params], np.ndarray]] = {
    "binary": binary,
    "votes_max": votes_max,
    "votes_log": votes_log,
    "votes_rank": votes_rank,
    "binary_idf": _with_idf(binary),
    "votes_max_idf": _with_idf(votes_max),
    "votes_log_idf": _with_idf(votes_log),
    "votes_rank_idf": _with_idf(votes_rank),
    "desc_tfidf": desc_tfidf,
    "desc_embed": desc_embed,
    "hybrid_tfidf": _hybrid(desc_tfidf),
    "hybrid_embed": _hybrid(desc_embed),
}


def vectorize(corpus: TagCorpus, method: str, params: Params) -> np.ndarray:
    """(n, m) row-normalised vectors for the named method."""
    if method not in METHODS:
        raise ValueError(
            f"unknown vectorization method {method!r}; valid methods: {sorted(METHODS)}"
        )
    weights = METHODS[method](corpus, params)
    norms = np.linalg.norm(weights, axis=1, keepdims=True)
    return weights / np.where(norms > 0, norms, 1.0)
