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
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from backend.app.db import DB_PATH
from pipeline.config import ARTIFACTS_DIR

SIMILARITY_DECIMALS = 10  # ties are decided by game_id, so last-bit float noise must not matter

Params = Mapping[str, Any]


@dataclass(frozen=True)
class TagCorpus:
    game_ids: np.ndarray        # (n,) ordered ascending
    titles: list[str]
    tags: list[str]             # (m,) sorted
    votes: np.ndarray           # (n, m) float, 0 where the tag is absent
    order: np.ndarray           # (n, m) 1-based rank in Steam's own tag order, 0 if absent
    descriptions: list[str]

    @property
    def present(self) -> np.ndarray:
        return self.votes > 0


def load_corpus(db_path: Path | str = DB_PATH) -> TagCorpus:
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"  # never creates a file
    conn = sqlite3.connect(uri, uri=True)
    try:
        rows = conn.execute(
            "SELECT game_id, title, description, raw_tags_json "
            "FROM games ORDER BY game_id"
        ).fetchall()
    finally:
        conn.close()
    raw = [json.loads(r[3]) if r[3] else {} for r in rows]
    tags = sorted({t for tag_votes in raw for t in tag_votes})
    column = {t: j for j, t in enumerate(tags)}
    votes = np.zeros((len(rows), len(tags)))
    order = np.zeros((len(rows), len(tags)))
    for i, tag_votes in enumerate(raw):
        for position, (tag, count) in enumerate(tag_votes.items(), start=1):
            votes[i, column[tag]] = count
            order[i, column[tag]] = position
    return TagCorpus(
        game_ids=np.array([r[0] for r in rows]),
        titles=[r[1] for r in rows],
        tags=tags,
        votes=votes,
        order=order,
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
    """(depth + 1 - rank) / depth: ignores vote magnitude entirely.

    Rank is the tag's position in Steam's own list, which breaks vote ties the
    way Steam did.
    """
    depth = params["rank_depth"]
    weights = np.clip(depth + 1 - corpus.order, 0, None) / depth
    return np.where(corpus.present, weights, 0.0)


def tag_idf(present: np.ndarray) -> np.ndarray:
    """Smooth IDF (sklearn's formula): a tag every game has still scores 1."""
    n = present.shape[0]
    df = present.sum(axis=0)
    return np.log((1 + n) / (1 + df)) + 1.0


def _with_idf(base: Callable[[TagCorpus, Params], np.ndarray]):
    def weighted(corpus: TagCorpus, params: Params) -> np.ndarray:
        return base(corpus, params) * tag_idf(corpus.present)

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
    """Normalised sentence embeddings, cached by model, revision and text.

    `embedding_cache_dir` is an optional override that tests use to keep the
    cache out of data/artifacts.
    """
    model_name = params["embedding_model"]
    revision = params["embedding_revision"]
    cache_dir = Path(params.get("embedding_cache_dir", ARTIFACTS_DIR / "embeddings"))
    digest = hashlib.sha256(
        json.dumps([model_name, revision, texts], ensure_ascii=False).encode()
    ).hexdigest()[:16]
    cache_file = cache_dir / f"{model_name.replace('/', '_')}-{digest}.npy"
    if cache_file.exists():
        return np.load(cache_file)

    from sentence_transformers import SentenceTransformer  # optional dependency

    model = SentenceTransformer(  # REL 2: pinned revision, no GPU nondeterminism
        model_name, revision=revision, device="cpu"
    )
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    cache_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=cache_dir, suffix=".tmp")
    with os.fdopen(fd, "wb") as fh:
        np.save(fh, vectors)
    os.replace(tmp_name, cache_file)  # atomic: a crash never leaves a torn cache
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


def _blank_descriptions(corpus: TagCorpus) -> np.ndarray:
    return np.array([not d.strip() for d in corpus.descriptions])[:, None]


def _from_relevance(
    corpus: TagCorpus, relevance: np.ndarray, params: Params
) -> np.ndarray:
    """Rescale within each game; a blank description says nothing (relevance 0)."""
    scaled = _rescale_within_game(relevance, corpus.present)
    scaled = np.where(_blank_descriptions(corpus), 0.0, scaled)
    return _description_weight(scaled, corpus.present, params)


def desc_tfidf(corpus: TagCorpus, params: Params) -> np.ndarray:
    return _from_relevance(corpus, tfidf_relevance(corpus), params)


def desc_embed(corpus: TagCorpus, params: Params) -> np.ndarray:
    return _from_relevance(corpus, embedding_relevance(corpus, params), params)


def _hybrid(description_method: Callable[[TagCorpus, Params], np.ndarray]):
    def blended(corpus: TagCorpus, params: Params) -> np.ndarray:
        alpha = params["hybrid_alpha"]
        return alpha * votes_log(corpus, params) + (1 - alpha) * description_method(
            corpus, params
        )

    return blended


EMBEDDING_METHODS = frozenset({"desc_embed", "hybrid_embed"})
TFIDF_METHODS = frozenset({"desc_tfidf", "hybrid_tfidf"})

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


def neighbor_indices(vectors: np.ndarray, k: int) -> np.ndarray:
    """(n, k) row indices of each game's k most similar other games, best first.

    Rows are in ascending game_id, so the stable sort breaks equal (rounded)
    similarities by game_id.
    """
    n = len(vectors)
    if not 0 < k < n:
        raise ValueError(f"need 0 < k < {n} games, got k={k}")
    sim = np.round(vectors @ vectors.T, SIMILARITY_DECIMALS)
    np.fill_diagonal(sim, -np.inf)
    return np.argsort(-sim, axis=1, kind="stable")[:, :k]
