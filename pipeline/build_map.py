"""Build the fixed game map: neighbours, 2D layout and clusters (GM 1, REL 2).

    python -m pipeline.build_map [--publish] [--version-id ID]

The default is a dry run: it builds, validates against the games table and
writes data/artifacts/map_<version>.json. Only `--publish` writes to the
database, through pipeline.publish.

Shape of the data:
    vectors  (n, m) L2-normalised rows from pipeline.vectorize, so a dot
             product is the cosine similarity
    game_ids (n,) ascending, one per row

Every step is deterministic: the same corpus and config give the same map.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA

from backend.app.db import DB_PATH
from pipeline import publish
from pipeline.config import load_config
from pipeline.vectorize import ARTIFACTS_DIR, TagCorpus, load_corpus, vectorize

SIMILARITY_DECIMALS = 10  # ties are decided by game_id, so last-bit float noise must not matter


@dataclass(frozen=True)
class MapBuild:
    clusters: list[dict]
    positions: list[dict]
    neighbors: list[dict]
    explained_variance_ratio: tuple[float, float]
    cluster_sizes: tuple[int, ...]
    collisions_moved: int


def nearest_neighbors(vectors: np.ndarray, game_ids: np.ndarray, k: int) -> list[dict]:
    """Each game's k most similar other games, best first, ties by game_id."""
    if not 0 < k < len(game_ids):
        raise ValueError(f"need 0 < k < {len(game_ids)} games, got k={k}")
    sim = np.round(vectors @ vectors.T, SIMILARITY_DECIMALS)
    np.fill_diagonal(sim, -np.inf)
    out = []
    for row in range(len(game_ids)):
        best = np.lexsort((game_ids, -sim[row]))[:k]
        for rank, col in enumerate(best, start=1):
            out.append(
                {
                    "game_id": int(game_ids[row]),
                    "neighbor_game_id": int(game_ids[col]),
                    "similarity_score": float(sim[row, col]),
                    "rank": rank,
                }
            )
    return out


def layout_2d(
    vectors: np.ndarray, seed: int, extent: float
) -> tuple[np.ndarray, tuple[float, float]]:
    """(n, 2) PCA coordinates scaled so the largest |coordinate| is `extent`.

    Also returns the variance ratio each of the two axes explains.
    """
    pca = PCA(n_components=2, svd_solver="full", random_state=seed)
    coords = pca.fit_transform(vectors)
    peak = np.abs(coords).max()
    if peak > 0:
        coords = coords * (extent / peak)
    return coords, tuple(float(r) for r in pca.explained_variance_ratio_)


def separate_collisions(
    coords: np.ndarray, game_ids: np.ndarray, min_distance: float
) -> tuple[np.ndarray, int]:
    """Spread apart points that sit closer than `min_distance`.

    Games with identical tag vectors share one coordinate, which would hide all
    but one of them. Each group of mutually close points is placed on a small
    ring around its centre, in game_id order, so no two are closer than
    `min_distance`. A group is joined through chains of close points. Returns
    the new coordinates and how many points moved.
    """
    diff = coords[:, None, :] - coords[None, :, :]
    close = np.hypot(diff[..., 0], diff[..., 1]) < min_distance
    _, group = connected_components(csr_matrix(close), directed=False)

    out = coords.copy()
    moved = 0
    for g in np.unique(group):
        members = np.flatnonzero(group == g)
        if len(members) < 2:
            continue
        members = members[np.argsort(game_ids[members], kind="stable")]
        centre = coords[members].mean(axis=0)
        # Chord between ring neighbours is 2 r sin(pi/k); the factor adds float margin.
        radius = 1.001 * min_distance / (2 * np.sin(np.pi / len(members)))
        angles = 2 * np.pi * np.arange(len(members)) / len(members)
        out[members] = centre + radius * np.column_stack([np.cos(angles), np.sin(angles)])
        moved += len(members)
    return out, moved


def assign_clusters(vectors: np.ndarray, n_clusters: int, seed: int) -> np.ndarray:
    """K-Means on the full weighted vectors, not on the 2D coordinates."""
    return KMeans(n_clusters=n_clusters, random_state=seed, n_init=10).fit_predict(vectors)


def cluster_rows(n_clusters: int, colors: list[str]) -> list[dict]:
    """CL 1: never invent names; a human names the clusters after review."""
    return [
        {
            "cluster_id": i,
            "display_name": f"Cluster {i}",
            "color": colors[i],
            "description": "",
        }
        for i in range(n_clusters)
    ]


def build_map(corpus: TagCorpus, cfg: dict) -> MapBuild:
    vec_cfg, layout = cfg["vectorization"], cfg["layout"]
    seed, n_clusters = cfg["random_seed"], cfg["cluster_count"]
    vectors = vectorize(corpus, vec_cfg["method"], vec_cfg)

    coords, variance = layout_2d(vectors, seed, layout["coordinate_extent"])
    coords, moved = separate_collisions(
        coords, corpus.game_ids, layout["collision_min_distance"]
    )
    labels = assign_clusters(vectors, n_clusters, seed)
    positions = [
        {
            "game_id": int(gid),
            "x": float(x),
            "y": float(y),
            "cluster_id": int(label),
        }
        for gid, (x, y), label in zip(corpus.game_ids, coords, labels)
    ]
    return MapBuild(
        clusters=cluster_rows(n_clusters, layout["cluster_colors"]),
        positions=positions,
        neighbors=nearest_neighbors(vectors, corpus.game_ids, layout["neighbor_count"]),
        explained_variance_ratio=variance,
        cluster_sizes=tuple(int(c) for c in np.bincount(labels, minlength=n_clusters)),
        collisions_moved=moved,
    )


def corpus_hash(corpus: TagCorpus) -> str:
    """Fingerprint of the exact data the vectors were built from."""
    digest = hashlib.sha256()
    digest.update(corpus.game_ids.tobytes())
    digest.update(corpus.votes.tobytes())
    digest.update(json.dumps([corpus.titles, corpus.tags, corpus.descriptions]).encode())
    return digest.hexdigest()


def known_game_ids(db_path: Path) -> set[int]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return {r[0] for r in conn.execute("SELECT game_id FROM games")}
    finally:
        conn.close()


def summary(build: MapBuild, version: str, method: str) -> str:
    x_var, y_var = build.explained_variance_ratio
    return "\n".join(
        [
            f"map version: {version} (method {method})",
            f"games: {len(build.positions)}, neighbours/game: "
            f"{len(build.neighbors) // len(build.positions)}",
            f"PCA explained variance: PC1 {x_var:.3f}, PC2 {y_var:.3f}, "
            f"total {x_var + y_var:.3f}",
            f"cluster sizes: {list(build.cluster_sizes)}",
            f"collisions moved: {build.collisions_moved}",
        ]
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--publish", action="store_true", help="write and activate the map in the database")
    parser.add_argument("--version-id", help="defaults to map_version in the config")
    args = parser.parse_args(argv)

    cfg = load_config()
    version = args.version_id or cfg["map_version"]
    method = cfg["vectorization"]["method"]
    corpus = load_corpus(DB_PATH)
    build = build_map(corpus, cfg)
    publish.validate(
        build.clusters, build.positions, build.neighbors, known_game_ids(DB_PATH)
    )

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    artifact = ARTIFACTS_DIR / f"map_{version}.json"
    artifact.write_text(
        json.dumps(
            {
                "map_version": version,
                "clusters": build.clusters,
                "positions": build.positions,
                "neighbors": build.neighbors,
            }
        ),
        encoding="utf-8",
    )
    print(summary(build, version, method))
    print("validate: ok")
    print(f"artifact: {artifact}")

    if args.publish:
        publish.publish_map(
            version,
            build.clusters,
            build.positions,
            build.neighbors,
            dataset_hash=corpus_hash(corpus),
            config_snapshot=cfg,
            feature_artifact_ref=f"vectorization:{method}",
        )
        print(f"published {version}")
    else:
        print("dry run: nothing written to the database (use --publish)")


if __name__ == "__main__":
    main()
