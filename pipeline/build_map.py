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
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA

from backend.app.db import DB_PATH
from pipeline import publish
from pipeline.config import (
    ARTIFACTS_DIR,
    is_valid_version_id,
    load_config,
    vectorization_params,
)
from pipeline.vectorize import (
    SIMILARITY_DECIMALS,
    TagCorpus,
    load_corpus,
    neighbor_indices,
    vectorize,
)

MAX_SEPARATION_PASSES = 100


@dataclass(frozen=True)
class MapBuild:
    clusters: list[dict]
    positions: list[dict]
    neighbors: list[dict]
    explained_variance_ratio: tuple[float, float]
    cluster_sizes: tuple[int, ...]
    collisions_moved: int


def nearest_neighbors(vectors: np.ndarray, game_ids: np.ndarray, k: int) -> list[dict]:
    """Each game's k most similar other games as publish-ready rows, best first."""
    best = neighbor_indices(vectors, k)
    scores = np.round(np.einsum("ij,ikj->ik", vectors, vectors[best]), SIMILARITY_DECIMALS)
    return [
        {
            "game_id": int(game_ids[row]),
            "neighbor_game_id": int(game_ids[col]),
            "similarity_score": float(scores[row, rank]),
            "rank": rank + 1,
        }
        for row in range(len(game_ids))
        for rank, col in enumerate(best[row])
    ]


def layout_2d(vectors: np.ndarray, extent: float) -> tuple[np.ndarray, tuple[float, float]]:
    """(n, 2) PCA coordinates scaled so the largest |coordinate| is `extent`.

    Also returns the variance ratio each of the two axes explains. The full
    SVD solver is deterministic, so no seed is involved. Collision separation
    afterwards can push a point slightly past `extent`.
    """
    pca = PCA(n_components=2, svd_solver="full")
    coords = pca.fit_transform(vectors)
    peak = np.abs(coords).max()
    if peak > 0:
        coords = coords * (extent / peak)
    return coords, tuple(float(r) for r in pca.explained_variance_ratio_)


def _min_pairwise_distance(coords: np.ndarray) -> float:
    diff = coords[:, None, :] - coords[None, :, :]
    dist = np.hypot(diff[..., 0], diff[..., 1])
    np.fill_diagonal(dist, np.inf)
    return float(dist.min()) if len(coords) > 1 else float("inf")


def separate_collisions(
    coords: np.ndarray, game_ids: np.ndarray, min_distance: float
) -> tuple[np.ndarray, int]:
    """Spread apart points that sit closer than `min_distance`.

    Games with identical tag vectors share one coordinate, which would hide all
    but one of them. Each group of mutually close points (joined through chains
    of close points) is placed on a small ring around its centre, in game_id
    order. A ring can land near a point outside its group, so grouping and
    placement repeat until a pass moves nothing.

    Guarantee: on return every pair of points is at least `min_distance` apart,
    or this raises. Points can end slightly farther from the origin than they
    started. Returns the new coordinates and how many distinct points moved.
    """
    out = coords.copy()
    moved: set[int] = set()
    for _ in range(MAX_SEPARATION_PASSES):
        diff = out[:, None, :] - out[None, :, :]
        close = np.hypot(diff[..., 0], diff[..., 1]) < min_distance
        _, group = connected_components(csr_matrix(close), directed=False)
        placed = out.copy()
        changed = False
        for g in np.unique(group):
            members = np.flatnonzero(group == g)
            if len(members) < 2:
                continue
            members = members[np.argsort(game_ids[members], kind="stable")]
            centre = out[members].mean(axis=0)
            # Chord between ring neighbours is 2 r sin(pi/k); the factor adds float margin.
            radius = 1.001 * min_distance / (2 * np.sin(np.pi / len(members)))
            angles = 2 * np.pi * np.arange(len(members)) / len(members)
            placed[members] = centre + radius * np.column_stack([np.cos(angles), np.sin(angles)])
            moved.update(members.tolist())
            changed = True
        out = placed
        if not changed:
            break
    else:
        raise RuntimeError(
            f"collision separation did not settle in {MAX_SEPARATION_PASSES} passes"
        )
    closest = _min_pairwise_distance(out)
    if closest < min_distance:
        raise RuntimeError(
            f"collision separation left two games {closest:.6g} apart, "
            f"below collision_min_distance {min_distance}"
        )
    return out, len(moved)


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
    vectors = vectorize(corpus, vec_cfg["method"], vectorization_params(cfg))

    coords, variance = layout_2d(vectors, layout["coordinate_extent"])
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
    digest.update(corpus.order.tobytes())
    digest.update(json.dumps([corpus.titles, corpus.tags, corpus.descriptions]).encode())
    return digest.hexdigest()


def map_version_exists(db_path: Path, version: str) -> bool:
    conn = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        return conn.execute(
            "SELECT 1 FROM map_versions WHERE map_version_id = ?", (version,)
        ).fetchone() is not None
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
    if not is_valid_version_id(version):
        parser.error("--version-id must match [A-Za-z0-9._-]+ and not contain '..'")
    method = cfg["vectorization"]["method"]
    if map_version_exists(DB_PATH, version):
        if args.publish:
            sys.exit(
                f"map version {version!r} already exists in the database; "
                "choose a new --version-id or map_version. Nothing was written."
            )
        print(
            f"WARNING: map version {version!r} already exists; "
            "--publish would refuse it. Use a new --version-id or map_version."
        )
    corpus = load_corpus(DB_PATH)
    build = build_map(corpus, cfg)
    publish.validate(
        build.clusters, build.positions, build.neighbors, set(corpus.game_ids.tolist())
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
            config_snapshot={**cfg, "map_version": version},
            feature_artifact_ref=f"vectorization:{method}",
        )
        print(f"published {version}")
    else:
        print("dry run: nothing written to the database (use --publish)")


if __name__ == "__main__":
    main()
