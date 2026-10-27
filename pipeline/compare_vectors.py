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
from pathlib import Path

import numpy as np
import yaml

from backend.app.db import DB_PATH
from pipeline.config import ARTIFACTS_DIR, REPO_ROOT, load_config, vectorization_params
from pipeline.vectorize import (
    EMBEDDING_METHODS,
    METHODS,
    TFIDF_METHODS,
    TagCorpus,
    load_corpus,
    neighbor_indices,
    tfidf_relevance,
    vectorize,
)

PAIRS_PATH = REPO_ROOT / "config" / "similar_pairs.yaml"
VECTORS_DIR = ARTIFACTS_DIR / "vectors"
REPORT_PATH = ARTIFACTS_DIR / "vector_comparison.md"
PAIR_K = 15
GENRE_K = 10
PROBES = ["Apex Legends™", "ELDEN RING", "Factorio", "Slay the Spire", "Resident Evil 2"]


def load_genres(db_path: Path, game_ids: np.ndarray) -> list[set[str]]:
    index = {int(g): i for i, g in enumerate(game_ids)}
    genres: list[set[str]] = [set() for _ in game_ids]
    conn = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT gf.game_id, f.name FROM game_features gf "
            "JOIN features f ON f.feature_id = gf.feature_id WHERE f.category = 'genre'"
        ).fetchall()
    finally:
        conn.close()
    for game_id, name in rows:
        genres[index[game_id]].add(name)
    return genres


def read_pair_titles(path: Path = PAIRS_PATH) -> list[tuple[str, str]]:
    return [(a, b) for a, b in yaml.safe_load(path.read_text("utf-8"))]


def resolve_pairs(
    corpus: TagCorpus, titles: list[tuple[str, str]]
) -> tuple[list[tuple[int, int]], list[str]]:
    """Row-index pairs for the titles present, plus the titles that are not."""
    row_of = {title: i for i, title in enumerate(corpus.titles)}
    pairs, missing = [], []
    for a, b in titles:
        absent = [t for t in (a, b) if t not in row_of]
        if absent:
            missing += absent
        else:
            pairs.append((row_of[a], row_of[b]))
    return pairs, missing


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


def mean_genre_jaccard(neighbors: np.ndarray, genres: list[set[str]], k: int) -> float:
    top = neighbors[:, :k]
    return float(np.mean([jaccard(genres[i], genres[j]) for i, row in enumerate(top) for j in row]))


def random_genre_jaccard(genres: list[set[str]], seed: int, k: int) -> float:
    rng = np.random.default_rng(seed)
    n = len(genres)
    draws = [
        jaccard(genres[i], genres[j])
        for i in range(n)
        for j in rng.choice(np.delete(np.arange(n), i), k, replace=False)
    ]
    return float(np.mean(draws))


def overlap_at(a: np.ndarray, b: np.ndarray, k: int) -> float:
    return float(np.mean([len(set(x[:k]) & set(y[:k])) / k for x, y in zip(a, b)]))


def coverage(relevance: np.ndarray, present: np.ndarray) -> float:
    return float(((relevance > 0) & present).sum() / present.sum())


def probe_rows(corpus: TagCorpus) -> tuple[dict[str, int], list[str]]:
    row_of = {t: i for i, t in enumerate(corpus.titles)}
    found = {t: row_of[t] for t in PROBES if t in row_of}
    return found, [t for t in PROBES if t not in row_of]


def save_vectors(corpus: TagCorpus, matrices: dict[str, np.ndarray]) -> None:
    VECTORS_DIR.mkdir(parents=True, exist_ok=True)
    np.save(VECTORS_DIR / "game_ids.npy", corpus.game_ids)
    (VECTORS_DIR / "tags.json").write_text(
        json.dumps(corpus.tags, ensure_ascii=False), encoding="utf-8"
    )
    for method, matrix in matrices.items():
        np.save(VECTORS_DIR / f"{method}.npy", matrix)


def table(header: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return lines + [""]


def build_report(
    corpus: TagCorpus,
    methods: list[str],
    neighbors: dict[str, np.ndarray],
    pair_titles: list[tuple[str, str]],
    genres: list[set[str]],
    random_baseline: float,
    tfidf_coverage: float | None,
    notes: list[str],
) -> str:
    """Pure rendering: every input is already computed, nothing is read or written."""
    pairs, missing_pair_titles = resolve_pairs(corpus, pair_titles)
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
        f"Mutual = each game is in the other's top-{PAIR_K}. "
        "One-way = either direction counted separately.",
        "",
    ]
    if missing_pair_titles:
        out += [
            "Not in this dataset, so their pairs were skipped: "
            + "; ".join(missing_pair_titles),
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
        f"Random-neighbour baseline: {random_baseline:.3f}",
        "",
    ]
    out += table(
        ["method", "mean genre Jaccard"],
        [[m, f"{mean_genre_jaccard(neighbors[m], genres, GENRE_K):.3f}"] for m in methods],
    )

    out += [f"## Method vs method: mean overlap@{GENRE_K} of neighbour lists", ""]
    out += table(
        [""] + methods,
        [
            [a] + [f"{overlap_at(neighbors[a], neighbors[b], GENRE_K):.2f}" for b in methods]
            for a in methods
        ],
    )

    if tfidf_coverage is not None:
        out += [
            "## Description coverage",
            "",
            "Fraction of present (game, tag) pairs with nonzero raw tf-idf relevance.",
            "",
        ]
        out += table(["method", "coverage"], [["desc_tfidf", f"{tfidf_coverage:.3f}"]])

    found, missing_probes = probe_rows(corpus)
    out += [f"## Probe games: top-5 neighbours", ""]
    if missing_probes:
        out += ["Not in this dataset: " + "; ".join(missing_probes), ""]
    for title, row in found.items():
        out.append(f"### {title}")
        out.append("")
        for m in methods:
            names = "; ".join(corpus.titles[j] for j in neighbors[m][row][:5])
            out.append(f"- **{m}**: {names}")
        out.append("")
    return "\n".join(out)


def default_methods() -> tuple[list[str], list[str]]:
    if importlib.util.find_spec("sentence_transformers"):
        return list(METHODS), ["sentence-transformers is installed: embedding methods included."]
    return (
        [m for m in METHODS if m not in EMBEDDING_METHODS],
        ["sentence-transformers is NOT installed: desc_embed and hybrid_embed were skipped."],
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--methods", nargs="+", choices=sorted(METHODS))
    args = parser.parse_args(argv)

    cfg = load_config()
    params = vectorization_params(cfg)
    methods, notes = (args.methods, ["Methods chosen with --methods."]) if args.methods else default_methods()
    corpus = load_corpus(DB_PATH)
    matrices = {m: vectorize(corpus, m, params) for m in methods}
    save_vectors(corpus, matrices)
    neighbors = {m: neighbor_indices(v, PAIR_K) for m, v in matrices.items()}
    genres = load_genres(DB_PATH, corpus.game_ids)
    uses_tfidf = any(m in TFIDF_METHODS for m in methods)
    report = build_report(
        corpus=corpus,
        methods=methods,
        neighbors=neighbors,
        pair_titles=read_pair_titles(),
        genres=genres,
        random_baseline=random_genre_jaccard(genres, cfg["random_seed"], GENRE_K),
        tfidf_coverage=coverage(tfidf_relevance(corpus), corpus.present) if uses_tfidf else None,
        notes=notes,
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"Report written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
