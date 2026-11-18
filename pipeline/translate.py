"""
Map v4: giving games WITHOUT Steam tag votes a place on the v3 map.

Map v3 (hybrid_max) only works for Steam games that have tag votes. About
179,000 games have none: the IGDB-only games and the Steam games with no
tags (Overwatch 2, Marvel Rivals, THE FINALS). This file holds the pieces
that let them join the map WITHOUT changing anything about v3:

  1. Translator   learns, from games that have both, how "IGDB-style data"
                  (features + a description) turns into a v3 vector.
  2. csls_topk    picks each new game's recommendations among the v3 games,
                  while marking down "hub" games that are close to everything.
  3. place_games  finds each new game a spot next to its recommendations on
                  the v3 map, then spreads crowded spots out a little.
                  v3 points never move.

Everything here is plain NumPy / SciPy with no randomness except values
seeded by game_id, so two builds give the same answer (REL 2).

The numbers behind each choice (why ridge, why CSLS, why this placement)
are in docs/map-v4.md.
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
from scipy.spatial import cKDTree

from pipeline.vectorize import SIMILARITY_DECIMALS

BLOCK = 512   # rows scored at a time, so memory stays at BLOCK x pool, not n x pool


def unit_rows(m: np.ndarray) -> np.ndarray:
    """Scale every row to length 1. An all-zero row stays all zeros (no divide by zero)."""
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.where(norms > 0, norms, 1.0)


# ===========================================================================
# 1. the translator
# ===========================================================================

class Translator:
    """Ridge regression from [features (0/1), description embedding] to a v3 vector.

    Why ridge: it is solved in one step (no training loop, no random start),
    takes seconds, and was as good as anything fancier we tried (a small
    neural net was only 2 points better).

    fit() wants:
      features   sparse (n, F) 0/1 matrix, one column per feature in the database
      text       dense (n, 384) description embeddings (zeros = no description)
      targets    dense (n, D) unit-length v3 vectors of the same games
    """

    def __init__(self, ridge_lambda: float = 10.0, min_feature_games: int = 5):
        self.ridge_lambda = float(ridge_lambda)
        self.min_feature_games = int(min_feature_games)
        self.columns: np.ndarray | None = None   # which feature columns the model uses
        self.weights: np.ndarray | None = None   # (kept features + text dims, D)

    def _inputs(self, features, text) -> sp.csr_matrix:
        features = sp.csr_matrix(features)[:, self.columns]
        features.data[:] = 1.0                    # presence only, never counts
        return sp.hstack([features, sp.csr_matrix(np.asarray(text, dtype=np.float64))]).tocsr()

    def fit(self, features, text, targets) -> "Translator":
        # Features almost nobody has just add noise, so keep the ones at least
        # min_feature_games training games share.
        counts = np.asarray((sp.csr_matrix(features) > 0).sum(axis=0)).ravel()
        self.columns = np.flatnonzero(counts >= self.min_feature_games)
        x = self._inputs(features, text)
        # The closed-form ridge answer: W = (X'X + lambda I)^-1 X'Y
        xtx = (x.T @ x).toarray()
        xty = np.asarray(x.T @ np.asarray(targets, dtype=np.float64))
        xtx[np.diag_indices_from(xtx)] += self.ridge_lambda
        self.weights = np.linalg.solve(xtx, xty)
        return self

    def predict(self, features, text) -> np.ndarray:
        """v3-space vectors for new games, unit length. All zeros = could not translate."""
        if self.weights is None:
            raise RuntimeError("call fit() before predict()")
        out = np.asarray(self._inputs(features, text) @ self.weights)
        # A v3 vector never has negative values, so anything below 0 is noise.
        return unit_rows(np.maximum(out, 0.0)).astype(np.float32)


# ===========================================================================
# 2. recommendations
# ===========================================================================

def _best_k(score: np.ndarray, k: int, pool_ids: np.ndarray) -> np.ndarray:
    """Indices of the k best columns of each row. Ties go to the lower game_id."""
    score = np.round(score, SIMILARITY_DECIMALS)   # same rule as vectorize.neighbor_indices
    kth = -np.partition(-score, k - 1, axis=1)[:, k - 1]
    out = np.empty((len(score), k), dtype=np.int64)
    for r in range(len(score)):
        cols = np.flatnonzero(score[r] >= kth[r])
        out[r] = cols[np.lexsort((pool_ids[cols], -score[r, cols]))[:k]]
    return out


def hub_scores(pool: np.ndarray, new: np.ndarray, k: int) -> np.ndarray:
    """For each pool (v3) game: its mean cosine to the k translated games closest to it.

    A high value means "this v3 game is close to lots of translated games",
    which is what a hub looks like. CSLS subtracts it.
    """
    out = np.empty(len(pool), dtype=np.float64)
    for s in range(0, len(pool), BLOCK):
        sim = pool[s:s + BLOCK] @ new.T
        out[s:s + BLOCK] = -np.partition(-sim, k - 1, axis=1)[:, :k].mean(axis=1)
    return out


def csls_topk(new: np.ndarray, pool: np.ndarray, pool_ids: np.ndarray, hubs: np.ndarray, k: int):
    """Each new game's k best pool games by CSLS, best first.

    CSLS score = 2 x cosine - hub score of the pool game. Without it, a few
    v3 games were the top recommendation of over 1,000 new games each; with
    it the biggest hub drops to about 670 and 91% of v3 games get used
    instead of 66%, with the same recommendation quality.

    Returns (indices into pool, plain cosine of each pick, best plain cosine).
    The plain cosine is what we store and show; CSLS only decides the order.
    """
    idx = np.empty((len(new), k), dtype=np.int64)
    cos = np.empty((len(new), k), dtype=np.float64)
    best = np.empty(len(new), dtype=np.float64)
    for s in range(0, len(new), BLOCK):
        sim = new[s:s + BLOCK] @ pool.T
        pick = _best_k(2 * sim - hubs[None, :], k, pool_ids)
        idx[s:s + BLOCK] = pick
        cos[s:s + BLOCK] = np.take_along_axis(sim, pick, axis=1)
        best[s:s + BLOCK] = sim.max(axis=1)
    return idx, cos, best


# ===========================================================================
# 3. placement
# ===========================================================================

def group_targets(rec_xy: np.ndarray, rec_sim: np.ndarray, radius: float, power: float) -> np.ndarray:
    """Where each new game should go: inside the biggest group of its recommendations.

    rec_xy  (n, k, 2) map positions of each game's k recommendations
    rec_sim (n, k)    their similarity

    Why not just the average of the k positions: when the recommendations sit
    on two or three different islands, the average lands in between, in a
    spot that has nothing to do with the game. So instead we look for the
    recommendations that sit within `radius` of each other, weight them by
    similarity^power, pick the heaviest group, and use its weighted middle.
    """
    out = np.empty((len(rec_xy), 2))
    weight = np.maximum(rec_sim, 0.0) ** power + 1e-12
    for i in range(len(rec_xy)):
        p, w = rec_xy[i], weight[i]
        dist = np.linalg.norm(p[:, None, :] - p[None, :, :], axis=2)
        support = (dist <= radius) @ w          # weight of the group around each recommendation
        centre = int(np.argmax(support))        # ties -> the better recommendation (lists are best first)
        members = dist[centre] <= radius
        out[i] = np.average(p[members], axis=0, weights=w[members])
    return out


def spread_out(fixed_xy: np.ndarray, targets: np.ndarray, seeds: np.ndarray, settings: dict) -> np.ndarray:
    """Move new points apart where they crowd, keeping each near its target.

    fixed_xy  v3 positions. They push but are never moved.
    targets   where each new game wants to be (from group_targets)
    seeds     one integer per new game (its game_id), so the start is the
              same on every machine

    Each new game starts on a small ring around its target, then for a set
    number of steps it is pushed away from neighbours that are closer than
    the local spacing of the v3 map, and pulled back toward its target.
    """
    tree_fixed = cKDTree(fixed_xy)
    lo, hi = settings["spacing_min"], settings["spacing_max"]
    spacing = tree_fixed.query(targets, k=settings["spacing_neighbor"])[0][:, -1]
    spacing = np.clip(spacing, lo, hi)
    angle = np.array([np.random.default_rng(int(s)).uniform(0, 2 * np.pi) for s in seeds])
    pos = targets + np.column_stack([np.cos(angle), np.sin(angle)]) * spacing[:, None]
    n_fixed = len(fixed_xy)
    k = settings["spread_neighbors"] + 1        # +1 because a point finds itself first
    for _ in range(settings["spread_steps"]):
        everything = np.vstack([fixed_xy, pos])
        dist, idx = cKDTree(everything).query(pos, k=k)
        own = n_fixed + np.arange(len(pos))
        keep = idx != own[:, None]               # drop the point itself
        dist = np.where(keep, dist, np.inf)
        away = pos[:, None, :] - everything[idx]
        overlap = np.clip(spacing[:, None] - dist, 0.0, None)      # how much too close
        unit_away = away / np.maximum(dist, 1e-3)[..., None]
        push = (unit_away * overlap[..., None]).sum(axis=1)
        pos = pos + settings["push"] * push + settings["pull"] * (targets - pos)
    return pos


def colour_from_map(fixed_xy: np.ndarray, fixed_cluster: np.ndarray, points: np.ndarray,
                    k: int, n_clusters: int) -> np.ndarray:
    """Cluster of each new point = the most common cluster among its k nearest v3 points.

    That way a new dot always matches the colour of the area it sits in.
    Ties go to the lower cluster id.
    """
    _, near = cKDTree(fixed_xy).query(points, k=k)
    labels = fixed_cluster[near]
    counts = np.stack([(labels == c).sum(axis=1) for c in range(n_clusters)], axis=1)
    return counts.argmax(axis=1)
