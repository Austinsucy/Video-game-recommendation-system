"""Search category weights for category_weighted against the similar pairs (DATA 2, UDR 1).

    python -m pipeline.tune_weights [--rounds 3]

Coordinate search: one category at a time, try every value in WEIGHT_GRID and
keep the best, repeated for `--rounds` passes. A pair scores when each game is
in the other's top PAIR_K; ties between weight sets go to the lower geometric
mean of the pairs' worse ranks, then to the current weights.

Thirty-odd pairs are few enough to overfit, so the report also runs
leave-one-pair-out: tune on every pair but one, then check the held-out pair.
That held-out hit rate is the honest estimate of how the tuned weights do on
pairs nobody tuned for.

Prints a report and saves it to data/artifacts/weight_tuning.md. Nothing here
changes the config or the published map.
"""
from __future__ import annotations

import argparse

import numpy as np

from backend.app.db import DB_PATH
from pipeline.compare_vectors import read_pair_titles, resolve_pairs
from pipeline.config import ARTIFACTS_DIR, alias_lookup, load_config, vectorization_params
from pipeline.vectorize import TagCorpus, load_corpus, vectorize

REPORT_PATH = ARTIFACTS_DIR / "weight_tuning.md"
PAIR_K = 15
WEIGHT_GRID = (0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0)
N_SEQUEL_PAIRS = 40  # config/similar_pairs.yaml lists the 40 sequel pairs first

Pairs = list[tuple[int, int]]


def pair_ranks(vectors: np.ndarray, pairs: Pairs) -> np.ndarray:
    """Each pair's worse rank: how far down the two games are in each other's lists.

    Rank 1 is the most similar other game. A pair is mutual top-k when this is <= k.
    """
    sim = vectors @ vectors.T
    np.fill_diagonal(sim, -np.inf)
    return np.array(
        [max((sim[a] > sim[a, b]).sum(), (sim[b] > sim[b, a]).sum()) + 1 for a, b in pairs]
    )


def score(ranks: np.ndarray) -> tuple[int, float]:
    """(pairs in mutual top-k, -geometric mean rank): larger is better."""
    return int((ranks <= PAIR_K).sum()), -float(np.exp(np.log(ranks).mean()))


class Evaluator:
    def __init__(self, corpus: TagCorpus, params: dict):
        self.corpus, self.params = corpus, params

    def ranks(self, weights: dict, pairs: Pairs) -> np.ndarray:
        vectors = vectorize(self.corpus, "category_weighted", {**self.params, "category_weights": weights})
        return pair_ranks(vectors, pairs)


def coordinate_search(evaluate: Evaluator, start: dict, pairs: Pairs, rounds: int) -> dict:
    """Deterministic: categories in sorted order, a new value must strictly beat the current one."""
    best = dict(start)
    best_score = score(evaluate.ranks(best, pairs))
    for _ in range(rounds):
        changed = False
        for category in sorted(best):
            for value in WEIGHT_GRID:
                if value == best[category]:
                    continue
                trial = {**best, category: value}
                if not any(w > 0 for w in trial.values()):
                    continue
                trial_score = score(evaluate.ranks(trial, pairs))
                if trial_score > best_score:
                    best, best_score, changed = trial, trial_score, True
        if not changed:
            break
    return best


def leave_one_out(evaluate: Evaluator, start: dict, pairs: Pairs, rounds: int) -> list[bool]:
    """For each pair: tune on the others, then is the held-out pair mutual top-k?"""
    held_out_hits = []
    for i, pair in enumerate(pairs):
        tuned = coordinate_search(evaluate, start, pairs[:i] + pairs[i + 1:], rounds)
        held_out_hits.append(bool(evaluate.ranks(tuned, [pair])[0] <= PAIR_K))
    return held_out_hits


def table(header: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return lines + ["| " + " | ".join(r) + " |" for r in rows] + [""]


def hits(ranks: np.ndarray) -> str:
    return f"{int((ranks <= PAIR_K).sum())}/{len(ranks)}"


def build_report(
    titles: list[tuple[str, str]],
    start: dict,
    tuned: dict,
    start_ranks: np.ndarray,
    tuned_ranks: np.ndarray,
    baseline_method: str,
    baseline_ranks: np.ndarray,
    loo_hits: list[bool],
) -> str:
    """Pure rendering: every input is already computed."""
    seq, cross = slice(0, N_SEQUEL_PAIRS), slice(N_SEQUEL_PAIRS, None)
    out = [
        "# category_weighted weight tuning",
        "",
        f"{len(titles)} pairs ({N_SEQUEL_PAIRS} sequel, {len(titles) - N_SEQUEL_PAIRS} cross-studio). "
        f"A pair scores when both games are in each other's top {PAIR_K}. "
        f"Grid: {', '.join(str(w) for w in WEIGHT_GRID)}.",
        "",
        "## Scores",
        "",
    ]
    rows = [
        (f"category_weighted, config weights", start_ranks),
        (f"category_weighted, tuned weights", tuned_ranks),
        (f"{baseline_method} (configured method)", baseline_ranks),
    ]
    out += table(
        ["vectors", "sequel", "cross-studio", "all"],
        [[name, hits(r[seq]), hits(r[cross]), hits(r)] for name, r in rows],
    )
    loo = np.array(loo_hits)
    out += [
        "## Leave-one-pair-out (honest estimate)",
        "",
        "Weights tuned without each pair, then tested on it. Compare with the tuned "
        "score above: a large gap means the tuned weights fit these particular pairs.",
        "",
    ]
    out += table(
        ["", "sequel", "cross-studio", "all"],
        [["held-out hits", f"{int(loo[seq].sum())}/{len(loo[seq])}",
          f"{int(loo[cross].sum())}/{len(loo[cross])}", f"{int(loo.sum())}/{len(loo)}"]],
    )
    out += ["## Weights", ""]
    out += table(
        ["category", "config", "tuned"],
        [[c, f"{start[c]:g}", f"{tuned[c]:g}"] for c in sorted(start)],
    )
    out += ["## Pair ranks (worse of the two directions)", ""]
    out += table(
        ["pair", "config", "tuned", baseline_method],
        [[f"{a} / {b}", str(s), str(t), str(v)]
         for (a, b), s, t, v in zip(titles, start_ranks, tuned_ranks, baseline_ranks)],
    )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rounds", type=int, default=3, help="coordinate-search passes")
    args = parser.parse_args(argv)

    cfg = load_config()
    params = vectorization_params(cfg)
    corpus = load_corpus(DB_PATH, alias_lookup(cfg), cfg["vectorization"].get("text_field", "description"))
    titles = read_pair_titles()
    pairs, missing = resolve_pairs(corpus, titles)
    if missing:
        raise SystemExit(f"pairs name games that are not in the database: {missing}")

    evaluate = Evaluator(corpus, params)
    baseline = cfg["vectorization"]["method"]
    start = dict(cfg["category_weights"])
    tuned = coordinate_search(evaluate, start, pairs, args.rounds)
    print("tuned on all pairs; running leave-one-pair-out ...", flush=True)
    report = build_report(
        titles=titles,
        start=start,
        tuned=tuned,
        start_ranks=evaluate.ranks(start, pairs),
        tuned_ranks=evaluate.ranks(tuned, pairs),
        baseline_method=baseline,
        baseline_ranks=pair_ranks(vectorize(corpus, baseline, params), pairs),
        loo_hits=leave_one_out(evaluate, start, pairs, args.rounds),
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"Report written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
