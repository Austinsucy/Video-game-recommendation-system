"""Compare tag vectorization methods side by side (DATA 2, REL 2, MAINT 2).

    python -m pipeline.compare_vectors [--methods binary votes_log_idf ...]

Writes each method's matrix to data/artifacts/vectors/, prints a report and
saves it to data/artifacts/vector_comparison.md. Nothing here touches the
published map.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
from itertools import combinations
from pathlib import Path

import numpy as np
import yaml

from pipeline.config import load_config
from pipeline.vectorize import (
    ARTIFACTS_DIR,
    DEFAULT_DB_PATH,
    METHODS,
    REPO_ROOT,
    TagCorpus,
    embedding_relevance,
    load_corpus,
    tfidf_relevance,
    vectorize,
)

PAIRS_PATH = REPO_ROOT / "config" / "similar_pairs.yaml"
VECTORS_DIR = ARTIFACTS_DIR / "vectors"
REPORT_PATH = ARTIFACTS_DIR / "vector_comparison.md"
PAIR_K = 15
GENRE_K = 10
PROBES = ["Apex Legends™", "ELDEN RING", "Factorio", "Slay the Spire", "Resident Evil 2"]
EMBED_METHODS = ("desc_embed", "hybrid_embed")


def top_k_neighbors(vectors: np.ndarray, k: int) -> np.ndarray:
    """(n, k) row indices of each game's most cosine-similar other games."""
    unit = vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
    sim = unit @ unit.T
    np.fill_diagonal(sim, -np.inf)
    return np.argsort(-sim, axis=1, kind="stable")[:, :k]


def load_genres(db_path: Path, game_ids: np.ndarray) -> list[set[str]]:
    index = {int(g): i for i, g in enumerate(game_ids)}
    genres: list[set[str]] = [set() for _ in game_ids]
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT gf.game_id, f.name FROM game_features gf "
            "JOIN features f ON f.feature_id = gf.feature_id WHERE f.category = 'genre'"
        )
        for game_id, name in rows:
            genres[index[game_id]].add(name)
    return genres


def load_pairs(corpus: TagCorpus, path: Path = PAIRS_PATH) -> list[tuple[int, int]]:
    row_of = {title: i for i, title in enumerate(corpus.titles)}
    return [(row_of[a], row_of[b]) for a, b in yaml.safe_load(path.read_text("utf-8"))]


def pair_scores(neighbors: np.ndarray, pairs: list[tuple[int, int]]) -> tuple[float, float]:
    """(mutual fraction, one-directional fraction) of known pairs in top-k."""
    a_has_b = [b in neighbors[a] for a, b in pairs]
    b_has_a = [a in neighbors[b] for a, b in pairs]
    mutual = np.mean([x and y for x, y in zip(a_has_b, b_has_a)])
    one_way = np.mean(a_has_b + b_has_a)
    return float(mutual), float(one_way)


def jaccard(a: set[str], b: set[str]) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def mean_genre_jaccard(neighbors: np.ndarray, genres: list[set[str]]) -> float:
    top = neighbors[:, :GENRE_K]
    return float(np.mean([jaccard(genres[i], genres[j]) for i, row in enumerate(top) for j in row]))


def random_genre_jaccard(genres: list[set[str]], seed: int) -> float:
    rng = np.random.default_rng(seed)
    n = len(genres)
    draws = [
        jaccard(genres[i], genres[j])
        for i in range(n)
        for j in rng.choice(np.delete(np.arange(n), i), GENRE_K, replace=False)
    ]
    return float(np.mean(draws))


def overlap_at(a: np.ndarray, b: np.ndarray, k: int = 10) -> float:
    return float(np.mean([len(set(x[:k]) & set(y[:k])) / k for x, y in zip(a, b)]))


def coverage(relevance: np.ndarray, present: np.ndarray) -> float:
    return float(((relevance > 0) & present).sum() / present.sum())


def save_vectors(corpus: TagCorpus, matrices: dict[str, np.ndarray]) -> None:
    VECTORS_DIR.mkdir(parents=True, exist_ok=True)
    np.save(VECTORS_DIR / "game_ids.npy", corpus.game_ids)
    (VECTORS_DIR / "tags.json").write_text(json.dumps(corpus.tags, ensure_ascii=False))
    for method, matrix in matrices.items():
        np.save(VECTORS_DIR / f"{method}.npy", matrix)


def table(header: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return lines + [""]


def build_report(
    corpus: TagCorpus,
    params: dict,
    seed: int,
    methods: list[str],
    notes: list[str],
    db_path: Path,
) -> str:
    matrices = {m: vectorize(corpus, m, params) for m in methods}
    save_vectors(corpus, matrices)
    neighbors = {m: top_k_neighbors(v, PAIR_K) for m, v in matrices.items()}
    pairs = load_pairs(corpus)
    genres = load_genres(db_path, corpus.game_ids)
    baseline = random_genre_jaccard(genres, seed)

    out = [
        "# Tag vectorization comparison",
        "",
        f"{len(corpus.titles)} games, {len(corpus.tags)} tags. "
        f"Methods compared: {', '.join(methods)}.",
        "",
        *[f"- {n}" for n in notes],
        "",
        f"## Known-similar pairs (primary, {len(pairs)} DRAFT pairs, top-{PAIR_K})",
        "",
        "Mutual = each game is in the other's top-15. One-way = either direction counted separately.",
        "",
    ]
    scores = {m: pair_scores(neighbors[m], pairs) for m in methods}
    out += table(
        ["method", "mutual", "one-way"],
        [[m, f"{scores[m][0]:.2f}", f"{scores[m][1]:.2f}"] for m in methods],
    )

    out += [
        f"## Genre Jaccard of top-{GENRE_K} neighbours (secondary, BIASED)",
        "",
        "Biased: genre names overlap tag names, so methods that lean on those tags score higher "
        "without being better. Use as a sanity check only.",
        "",
        f"Random-neighbour baseline: {baseline:.3f}",
        "",
    ]
    out += table(
        ["method", "mean genre Jaccard"],
        [[m, f"{mean_genre_jaccard(neighbors[m], genres):.3f}"] for m in methods],
    )

    out += [f"## Method vs method: mean overlap@{GENRE_K} of neighbour lists", ""]
    grid = {(a, b): overlap_at(neighbors[a], neighbors[b]) for a, b in combinations(methods, 2)}
    out += table(
        [""] + methods,
        [
            [a] + [("1.00" if a == b else f"{grid.get((a, b), grid.get((b, a))):.2f}") for b in methods]
            for a in methods
        ],
    )

    present = corpus.present
    cover = []
    if "desc_tfidf" in methods or "hybrid_tfidf" in methods:
        cover.append(["desc_tfidf", coverage(tfidf_relevance(corpus), present)])
    if "desc_embed" in methods or "hybrid_embed" in methods:
        cover.append(["desc_embed", coverage(embedding_relevance(corpus, params), present)])
    if cover:
        out += [
            "## Description coverage",
            "",
            "Fraction of present (game, tag) pairs with nonzero raw description relevance. "
            "Embedding cosine is rarely exactly zero, so its coverage says little.",
            "",
        ]
        out += table(["method", "coverage"], [[m, f"{c:.3f}"] for m, c in cover])

    out += [f"## Probe games: top-5 neighbours", ""]
    row_of = {t: i for i, t in enumerate(corpus.titles)}
    for title in PROBES:
        out.append(f"### {title}")
        out.append("")
        for m in methods:
            names = "; ".join(corpus.titles[j] for j in neighbors[m][row_of[title]][:5])
            out.append(f"- **{m}**: {names}")
        out.append("")
    return "\n".join(out)


def default_methods() -> tuple[list[str], list[str]]:
    if importlib.util.find_spec("sentence_transformers"):
        return list(METHODS), ["sentence-transformers is installed: embedding methods included."]
    return (
        [m for m in METHODS if m not in EMBED_METHODS],
        ["sentence-transformers is NOT installed: desc_embed and hybrid_embed were skipped."],
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--methods", nargs="+", choices=sorted(METHODS))
    args = parser.parse_args(argv)

    cfg = load_config()
    methods, notes = (args.methods, ["Methods chosen with --methods."]) if args.methods else default_methods()
    corpus = load_corpus(DEFAULT_DB_PATH)
    report = build_report(corpus, cfg["vectorization"], cfg["random_seed"], methods, notes, DEFAULT_DB_PATH)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"Report written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
