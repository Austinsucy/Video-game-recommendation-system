"""Held-out check of the map v4 translator.

    python -m pipeline.eval_translation

Idea: merged games have BOTH an IGDB description and a real v3 vector, so we
can hide some of them, translate them from their IGDB data only, and see how
good their recommendations are compared with the ones v3 gives them.

Recommendation quality = average v3-space similarity between the game's TRUE
v3 vector and each recommended game, scaled so that
    0%   = 15 random v3 games
    100% = v3's own 15 recommendations for that game.

Compared against "description only" (what a text-only method gives an IGDB
game). Fails (exit code 1) if quality is under translation.evaluation.min_quality
or not min_gain_over_text times better than description only.
"""
from __future__ import annotations

import json
import sys

import numpy as np

from backend.app.db import DB_PATH
from pipeline.build_map_v4 import embed, igdb_view, read_base_map, read_games
from pipeline.config import ARTIFACTS_DIR, REPO_ROOT, alias_lookup, load_config, vectorization_params
from pipeline.translate import Translator
from pipeline.vectorize import load_corpus, neighbor_indices, vectorize

K = 15


def top_k(queries: np.ndarray, pool: np.ndarray, k: int, skip: np.ndarray) -> np.ndarray:
    """k best pool rows per query, never the query's own twin (skip[i])."""
    out = np.empty((len(queries), k), dtype=np.int64)
    for s in range(0, len(queries), 512):
        sim = queries[s:s + 512] @ pool.T
        sim[np.arange(len(sim)), skip[s:s + 512]] = -np.inf
        part = np.argpartition(-sim, k, axis=1)[:, :k]
        order = np.argsort(-np.take_along_axis(sim, part, axis=1), axis=1, kind="stable")
        out[s:s + 512] = np.take_along_axis(part, order, axis=1)
    return out


def evaluate(cfg: dict) -> dict:
    tcfg, ev = cfg["translation"], cfg["translation"]["evaluation"]
    params = vectorization_params(cfg)
    _, base, _ = read_base_map(REPO_ROOT / tcfg["base_map_db"])
    weighted = {c for c, w in cfg["category_weights"].items() if w}
    corpus = load_corpus(DB_PATH, alias_lookup(cfg), cfg["vectorization"]["text_field"],
                         only_with_votes=True, feature_categories=weighted)
    vectors = vectorize(corpus, cfg["vectorization"]["method"], params).astype(np.float32)
    on_v3 = np.array([g in base for g in corpus.game_ids])
    pool, pool_ids = vectors[on_v3], corpus.game_ids[on_v3]
    pool_text = embed([d for d, keep in zip(corpus.descriptions, on_v3) if keep], params)

    games = read_games(DB_PATH)
    pool_rows = np.array([games["row_of"][g] for g in pool_ids])
    merged = np.flatnonzero([games["raw_igdb"][i] is not None and games["source"][i] == "steam" for i in pool_rows])
    rng = np.random.default_rng(ev["seed"])
    test = np.sort(rng.choice(merged, size=min(ev["test_size"], len(merged) // 2), replace=False))
    train = np.setdiff1d(merged, test)

    f_train, t_train = igdb_view(games, pool_rows[train], cfg)
    f_test, t_test = igdb_view(games, pool_rows[test], cfg)
    e_train, e_test = embed(t_train, params), embed(t_test, params)
    model = Translator(tcfg["ridge_lambda"], tcfg["min_feature_games"]).fit(f_train, e_train, pool[train])
    q = model.predict(f_test, e_test)

    truth = pool[test]
    own = neighbor_indices(pool, K)[test]                     # v3's own lists
    rand = rng.integers(0, len(pool), size=(len(test), K))

    def score(nb):
        return float(np.mean(np.einsum("id,ikd->ik", truth, pool[nb])))

    def genre_overlap(nb):
        g = (games["features"][:, [j for j, (c, _) in enumerate(games["feature_keys"]) if c == "genre"]] > 0)
        g = g.toarray()[pool_rows]
        a, b = g[test][:, None, :], g[nb]
        union = (a | b).sum(-1)
        return float(np.mean(np.where(union > 0, (a & b).sum(-1) / np.maximum(union, 1), 0)))

    lo, hi = score(rand), score(own)
    ridge_nb = top_k(q, pool, K, test)
    text_nb = top_k(e_test, pool_text, K, test)
    result = {
        "test_games": int(len(test)), "train_games": int(len(train)),
        "ridge_quality": round((score(ridge_nb) - lo) / (hi - lo), 4),
        "description_only_quality": round((score(text_nb) - lo) / (hi - lo), 4),
        "genre_overlap": {"ridge": round(genre_overlap(ridge_nb), 3), "description_only": round(genre_overlap(text_nb), 3),
                          "v3": round(genre_overlap(own), 3), "random": round(genre_overlap(rand), 3)},
        "exact_v3_recs_ridge": round(float(np.mean([len(set(a) & set(b)) / K for a, b in zip(ridge_nb, own)])), 4),
    }
    result["gain_over_text"] = round(result["ridge_quality"] / max(result["description_only_quality"], 1e-9), 2)
    result["passed"] = bool(result["ridge_quality"] >= ev["min_quality"] and result["gain_over_text"] >= ev["min_gain_over_text"])
    return result


def main() -> None:
    result = evaluate(load_config())
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS_DIR / "translation_eval.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        sys.exit("translation check FAILED: see translation.evaluation in the config")


if __name__ == "__main__":
    main()
