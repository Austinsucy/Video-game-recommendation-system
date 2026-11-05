"""Build the data behind the Tag Vector Lab page from pipeline output (GM 1, REL 2).

    python -m pipeline.vector_lab --small PATH --full PATH \\
        [--text-field description|long_description] [--device cpu|cuda] \\
        [--out data/artifacts/vector_lab] [--page vector_lab.html]

--small is the 1,000-game database (build "1k") and --full the whole catalogue
(build "90k"). The full database is the universe: every game of the small one
is found in it by store_url, and all neighbour lists in the output use its row
numbers. For each build, every method in DEFAULT_METHODS vectorizes the full
corpus, games with no vector are left out, and the map is built by
pipeline.build_map, so the lab shows exactly what the pipeline produces.
--text-field and --device override the config for this run only. Nothing here
touches the published map. Collision spreading is applied only to builds within
publish.MAX_GAMES; above the cap the 1-unit spacing cannot be met.

Shape of the data:
    Run     one (build, method): the rows that have a vector, top-10 neighbours
            and their similarity, map coordinates, cluster, top tags
    output  meta.json, one `m_<build>_<method>.bin.gz.b64.txt` per run, a shared
            `shared.bin.gz.b64.txt`, and index.html if --page names the viewer page
Each .bin is named, 8-byte-aligned arrays; meta.json gives each array's dtype,
offset and length. gzip uses mtime 0, so equal inputs give equal bytes.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import json
import shutil
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from pipeline import compare_vectors as C
from pipeline import publish
from pipeline.build_map import build_map_from_vectors
from pipeline.config import ARTIFACTS_DIR, EMBEDDING_DEVICES, TEXT_FIELDS, load_config, vectorization_params
from pipeline.vectorize import TEXT_METHODS, TagCorpus, load_corpus_for, vectorize

DEFAULT_METHODS = ["votes_max", "desc_embed", "hybrid_embed", "hybrid_max", "semantic", "hybrid_semantic"]
SHOW_K, TOP_TAGS, RAW_TAGS = 10, 6, 10
NO_TAG = 65535
SMALL_LABEL, FULL_LABEL = "1k", "90k"


@dataclass(frozen=True)
class Build:
    label: str
    corpus: TagCorpus
    store_urls: list[str | None]
    rating_counts: np.ndarray       # (n,) int64, -1 where the database has none
    genres: list[set[str]]


@dataclass(frozen=True)
class Run:
    build: str
    method: str
    scores: dict                    # the scalar fields meta.json reports for the run
    rows: np.ndarray                # (n,) universe index of each game with a vector
    neighbors: np.ndarray           # (n, k) universe indices, best first
    sim: np.ndarray                 # (n, SHOW_K) cosine of the first SHOW_K neighbours
    xy: np.ndarray                  # (n, 2)
    cluster: np.ndarray             # (n,)
    tag_names: list[str] | None     # None when the method has no tag space
    tag_idx: np.ndarray | None      # (n, TOP_TAGS) column in tag_names
    tag_w: np.ndarray | None        # (n, TOP_TAGS) uint16 weight relative to the game's top tag


def load_build(label: str, db: Path, cfg: dict) -> Build:
    corpus = load_corpus_for(db, cfg)
    conn = sqlite3.connect(Path(db).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT store_url, rating_count FROM games ORDER BY game_id").fetchall()
    finally:
        conn.close()
    return Build(
        label=label,
        corpus=corpus,
        store_urls=[r[0] for r in rows],
        rating_counts=np.array([-1 if r[1] is None else r[1] for r in rows], dtype=np.int64),
        genres=C.load_genres(Path(db), corpus.game_ids),
    )


def universe_rows(build: Build, universe: Build) -> np.ndarray:
    """Universe row of each of the build's games, matched by store_url."""
    row_of = {u: i for i, u in enumerate(universe.store_urls)}
    found = np.array([row_of.get(u, -1) for u in build.store_urls], dtype=np.int64)
    if (found < 0).any():
        raise SystemExit(
            f"{int((found < 0).sum())} games of build {build.label!r} are not in "
            f"{universe.label!r} (matched by store_url); --full must contain every game of --small"
        )
    return found


def top_weights(weights: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """Each row's k largest columns and their weights relative to the row's largest, as uint16."""
    weights = np.pad(weights, ((0, 0), (0, max(0, k - weights.shape[1]))))
    order = np.argsort(-weights, axis=1, kind="stable")[:, :k]
    w = np.take_along_axis(weights, order, axis=1)
    peak = np.maximum(w[:, :1], 1e-12)
    return order.astype(np.uint16), np.round(65535 * np.clip(w / peak, 0, 1)).astype(np.uint16)


def run_method(
    build: Build, method: str, to_universe: np.ndarray, pairs: list[tuple[int, int]], cfg: dict
) -> Run:
    corpus, params = build.corpus, vectorization_params(cfg)
    vectors = vectorize(corpus, method, params)
    valid = np.flatnonzero(np.linalg.norm(vectors, axis=1) > 0)
    kept = vectors[valid]
    k = cfg["layout"]["neighbor_count"]
    spread = len(valid) <= publish.MAX_GAMES
    made = build_map_from_vectors(kept, corpus.game_ids[valid], cfg, spread_collisions=spread)

    # neighbours come out grouped by game, best first
    local = np.searchsorted(
        corpus.game_ids[valid], np.array([r["neighbor_game_id"] for r in made.neighbors])
    ).reshape(-1, k)
    sim = np.array([r["similarity_score"] for r in made.neighbors]).reshape(-1, k)
    full = np.full((len(vectors), k), -1, dtype=np.int64)
    full[valid] = valid[local]
    found = [(a, b) for a, b in pairs if full[a, 0] >= 0 and full[b, 0] >= 0]
    mutual, one_way = C.pair_scores(full, found) if found else (0.0, 0.0)

    if method == "semantic":
        tag_weights = None
    else:
        tag_weights = vectorize(corpus, "votes_max", params) if method in TEXT_METHODS else vectors
    scores = {
        "build": build.label, "method": method, "n": int(len(valid)),
        "pairMutual": mutual, "pairOneWay": one_way, "pairsFound": len(found),
        "genreJaccard": C.mean_genre_jaccard(local, [build.genres[i] for i in valid], C.GENRE_K),
        "keptTsne": made.neighbors_kept_on_map,
        "collisionsSpread": spread,
        "space": "none" if tag_weights is None else "tags",
    }
    tag_idx = tag_w = None
    if tag_weights is not None:
        tag_idx, tag_w = top_weights(tag_weights[valid], TOP_TAGS)
    return Run(
        build=build.label,
        method=method,
        scores=scores,
        rows=to_universe[valid],
        neighbors=to_universe[valid[local]],
        sim=sim[:, :SHOW_K],
        xy=np.array([[p["x"], p["y"]] for p in made.positions]),
        cluster=np.array([p["cluster_id"] for p in made.positions]),
        tag_names=None if tag_weights is None else corpus.tags,
        tag_idx=tag_idx,
        tag_w=tag_w,
    )


def write_bin(path: Path, arrays: list[tuple[str, np.ndarray]]) -> list[dict]:
    layout, buf = [], bytearray()
    for name, a in arrays:
        a = np.ascontiguousarray(a).ravel()
        buf += b"\0" * (-len(buf) % 8)
        layout.append({"name": name, "dtype": a.dtype.name, "offset": len(buf), "length": int(a.size)})
        buf += a.tobytes()
    path.write_text(base64.b64encode(gzip.compress(bytes(buf), 9, mtime=0)).decode())
    return layout


def top_sets(run: Run, first_rows: np.ndarray) -> dict[int, set[int]]:
    """Top-SHOW_K neighbours, by universe index, of each of the first build's games that has a vector."""
    pos = {int(u): i for i, u in enumerate(run.rows)}
    return {int(g): set(run.neighbors[pos[g], :SHOW_K].tolist()) for g in first_rows if int(g) in pos}


def overlap_matrix(tops: list[dict[int, set[int]]]) -> list[list[float]]:
    return [
        [
            float(np.mean([len(a[g] & b[g]) / SHOW_K for g in a.keys() & b.keys()]))
            for b in tops
        ]
        for a in tops
    ]


def write_lab(
    out: Path, builds: list[Build], runs: list[Run], to_universe: dict[str, np.ndarray], cfg: dict
) -> None:
    universe, first = builds[-1], builds[0]
    params = vectorization_params(cfg)
    first_rows = to_universe[first.label]
    keys = [f"{r.build}:{r.method}" for r in runs]
    tops = [top_sets(r, first_rows) for r in runs]
    overlap = overlap_matrix(tops)
    first_set = set(first_rows.tolist())
    scores = {key: dict(r.scores) for key, r in zip(keys, runs)}
    for key, r, top in zip(keys, runs, tops):
        if r.build != first.label:
            scores[key]["newcomers"] = float(np.mean([len(t - first_set) / SHOW_K for t in top.values()]))
            scores[key]["vs1k"] = overlap[keys.index(key)][keys.index(f"{first.label}:{r.method}")]

    all_tags = sorted({t for r in runs if r.tag_names for t in r.tag_names} | set(universe.corpus.tags))
    tag_id = {t: i for i, t in enumerate(all_tags)}

    n_universe = len(universe.corpus.game_ids)
    raw_idx = np.full((n_universe, RAW_TAGS), NO_TAG, dtype=np.uint16)
    raw_votes = np.zeros((n_universe, RAW_TAGS), dtype=np.uint32)
    present, tags = universe.corpus.present, universe.corpus.tags
    for i in range(n_universe):
        cols = np.flatnonzero(present[i])
        cols = cols[np.argsort(universe.corpus.order[i, cols])][:RAW_TAGS]
        raw_idx[i, : len(cols)] = [tag_id[tags[j]] for j in cols]
        raw_votes[i, : len(cols)] = universe.corpus.votes[i, cols]
    in_first = np.zeros(n_universe, dtype=np.uint8)
    in_first[first_rows] = 1
    genre_names = sorted({g for gs in universe.genres for g in gs})
    genre_id = {g: i for i, g in enumerate(genre_names)}

    out.mkdir(parents=True, exist_ok=True)
    # An unknown rating_count is stored as -1; clip it before the unsigned cast.
    shared = write_bin(out / "shared.bin.gz.b64.txt", [
        ("rawIdx", raw_idx), ("rawVotes", raw_votes),
        ("ratingCount", np.clip(universe.rating_counts, 0, 2**32 - 1).astype(np.uint32)),
        ("in1k", in_first),
    ])
    if cfg["cluster_count"] > 256:
        raise ValueError(f"cluster_count {cfg['cluster_count']} does not fit the uint8 cluster ids")
    meta = {
        "nUniverse": n_universe, "titles": universe.corpus.titles,
        "genres": ["".join(chr(65 + genre_id[g]) for g in sorted(gs)) for gs in universe.genres],
        "genreNames": genre_names, "tags": all_tags, "rawK": RAW_TAGS, "showK": SHOW_K, "topTags": TOP_TAGS,
        "pairK": cfg["layout"]["neighbor_count"], "genreK": C.GENRE_K, "alpha": params["hybrid_alpha"],
        "descriptionFloor": params["description_floor"], "textField": params["text_field"],
        "configMethod": params["method"], "clusterColors": cfg["layout"]["cluster_colors"],
        "methodOrder": keys, "overlap": overlap,
        "randomGenreJaccard": {first.label: C.random_genre_jaccard(first.genres, cfg["random_seed"], C.GENRE_K)},
        "shared": shared, "sharedFile": "shared.bin.gz.b64.txt", "methods": {},
    }
    for key, r in zip(keys, runs):
        arrays = [
            ("rows", r.rows.astype(np.uint32)),
            ("nb", r.neighbors[:, :SHOW_K].astype(np.uint32)),
            ("sim", np.round(32767 * np.clip(r.sim, -1, 1)).astype(np.int16)),
            ("xy", r.xy.astype(np.float32)),
            ("cluster", r.cluster.astype(np.uint8)),
        ]
        if r.tag_idx is not None:
            lut = np.array([tag_id[t] for t in r.tag_names], dtype=np.uint16)
            arrays += [("tagIdx", lut[r.tag_idx]), ("tagW", r.tag_w)]
        name = "m_" + key.replace(":", "_") + ".bin.gz.b64.txt"
        meta["methods"][key] = {**scores[key], "file": name, "layout": write_bin(out / name, arrays)}
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def build_lab(small: Path, full: Path, out: Path, cfg: dict, page: Path | None = None, log=print) -> list[Run]:
    t0 = time.time()
    loaded = [load_build(SMALL_LABEL, small, cfg), load_build(FULL_LABEL, full, cfg)]
    universe = loaded[-1]
    if len(set(universe.store_urls)) != len(universe.store_urls) or None in universe.store_urls:
        raise SystemExit(f"{universe.label!r} has missing or repeated store_url values, so it cannot be the universe")
    to_universe = {b.label: universe_rows(b, universe) for b in loaded}
    runs = []
    for b in loaded:
        pairs, _ = C.resolve_pairs(b.corpus, C.read_pair_titles())
        for method in DEFAULT_METHODS:
            start = time.time()
            r = run_method(b, method, to_universe[b.label], pairs, cfg)
            s = r.scores
            log(
                f"[{time.time() - t0:7.1f}s] {b.label}:{method} n={s['n']} "
                f"pairs={s['pairMutual']:.2f}/{s['pairOneWay']:.2f} on {s['pairsFound']} "
                f"genre={s['genreJaccard']:.3f} kept={s['keptTsne']:.2f} ({time.time() - start:.0f}s)"
                + ("" if s["collisionsSpread"] else " no collision spreading (over CON 3 cap)")
            )
            runs.append(r)
    write_lab(out, loaded, runs, to_universe, cfg)
    if page:
        shutil.copyfile(page, out / "index.html")
    log(f"[{time.time() - t0:7.1f}s] wrote {out}")
    return runs


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--small", type=Path, required=True, help="the 1,000-game database")
    parser.add_argument("--full", type=Path, required=True, help="the whole catalogue; the universe of the output")
    parser.add_argument("--text-field", choices=TEXT_FIELDS, default="long_description",
                        help="text the description methods embed, for this run only")
    parser.add_argument("--device", choices=EMBEDDING_DEVICES, help="embedding device for this run only; overrides vectorization.embedding_device")
    parser.add_argument("--out", type=Path, default=ARTIFACTS_DIR / "vector_lab")
    parser.add_argument("--page", type=Path, help="viewer page to copy in as index.html; it is not in the repo")
    args = parser.parse_args(argv)

    cfg = load_config()
    cfg["vectorization"]["text_field"] = args.text_field
    if args.device:
        cfg["vectorization"]["embedding_device"] = args.device
    if args.page and not args.page.is_file():
        parser.error(f"--page {args.page} does not exist")
    build_lab(args.small, args.full, args.out, cfg, args.page)


if __name__ == "__main__":
    main()
