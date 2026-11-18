"""Build map v4: map v3 kept exactly, plus every game v3 could not place.

    python -m pipeline.build_map_v4                 dry run: build, validate, write a report
    python -m pipeline.build_map_v4 --publish       also write v4 into data/games.db and
                                                    export it to data/map_v4.db

data/map.db (the v3 map the website reads) is NOT touched. Switching the
website to v4 is a separate, reviewed step (Kayne).

What it does, in order (the reasons and numbers are in docs/map-v4.md):
  1. Rebuild the v3 vectors (hybrid_max) for the Steam games with votes,
     exactly the way build_map does. Their positions and clusters are copied
     from the published v3 map, never recomputed.
  2. Train the translator on merged games: their IGDB features + IGDB text
     on one side, their real v3 vector on the other.
  3. Translate every game without votes into v3 space.
  4. Recommendations for those games: the 15 best v3 games by CSLS.
     Steam games keep their own v3 lists, untouched by new games.
  5. Put the new games next to their recommendations on the v3 map.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
import scipy.sparse as sp

from backend.app.db import DB_PATH
from pipeline import publish
from pipeline.build_map import nearest_neighbors
from pipeline.config import (
    ARTIFACTS_DIR,
    REPO_ROOT,
    alias_lookup,
    is_valid_version_id,
    load_config,
    vectorization_params,
)
from pipeline.export_map import export_map_db
from pipeline.translate import (
    Translator,
    colour_from_map,
    csls_topk,
    group_targets,
    hub_scores,
    spread_out,
    unit_rows,
)
from pipeline.vectorize import _embed, load_corpus, vectorize

V4_MAP_DB = REPO_ROOT / "data" / "map_v4.db"
REPORT_PATH = REPO_ROOT / "data" / "map_v4_report.md"


def say(msg: str, t0: float) -> None:
    print(f"[{time.time() - t0:5.0f}s] {msg}", flush=True)


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------

def read_base_map(path: Path) -> tuple[str, dict[int, tuple[float, float, int]], list[dict]]:
    """The published v3 map: {game_id: (x, y, cluster_id)} and its clusters."""
    conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        version = conn.execute("SELECT map_version FROM map_info").fetchone()[0]
        games = {g: (x, y, c) for g, x, y, c in conn.execute("SELECT game_id, x, y, cluster_id FROM games")}
        clusters = [{"cluster_id": c, "display_name": name, "color": color, "description": ""}
                    for c, name, color in conn.execute("SELECT cluster_id, name, color FROM clusters ORDER BY cluster_id")]
    finally:
        conn.close()
    return version, games, clusters


def read_games(db_path: Path) -> dict:
    """Everything about every game that the translation needs, in game_id order."""
    conn = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT game_id, description, is_non_game, raw_igdb_json, primary_source, "
            "raw_tags_json IS NOT NULL FROM games ORDER BY game_id").fetchall()
        feats = conn.execute("SELECT feature_id, category, name FROM features ORDER BY feature_id").fetchall()
        links = conn.execute("SELECT game_id, feature_id FROM game_features").fetchall()
    finally:
        conn.close()
    gid = np.array([r[0] for r in rows])
    row_of = {g: i for i, g in enumerate(gid)}
    col_of = {f: j for j, (f, _, _) in enumerate(feats)}
    r = np.array([row_of[g] for g, _ in links])
    c = np.array([col_of[f] for _, f in links])
    features = sp.csr_matrix((np.ones(len(links)), (r, c)), shape=(len(gid), len(feats)))
    return {
        "game_id": gid,
        "row_of": row_of,
        "description": [row[1] or "" for row in rows],
        "non_game": np.array([row[2] for row in rows]),
        "raw_igdb": [json.loads(row[3]) if row[3] else None for row in rows],
        "source": np.array([row[4] for row in rows]),
        "has_votes": np.array([bool(row[5]) for row in rows]),
        "features": features,
        "feature_keys": [(cat, name) for _, cat, name in feats],
    }


def igdb_view(games: dict, rows: np.ndarray, cfg: dict) -> tuple[sp.csr_matrix, list[str]]:
    """The features and text a merged game would have if it were IGDB-only.

    Training has to look like the games we translate later, so a merged game
    is described by its IGDB lists and IGDB blurb, not by its Steam data.
    """
    from pipeline.igdb import platform_lookup, resolve_igdb_features
    from pipeline.ingest import FeatureRegistry

    aliases = alias_lookup(cfg)
    registry = FeatureRegistry(cfg)
    platforms = platform_lookup(cfg["sources"]["igdb"])
    col_of = {key: j for j, key in enumerate(games["feature_keys"])}
    ri, ci, texts = [], [], []
    for out_row, i in enumerate(rows):
        rec = games["raw_igdb"][i] or {}
        found, _ = resolve_igdb_features(rec, cfg, aliases, registry, platforms)
        for key in found:
            if key in col_of:
                ri.append(out_row)
                ci.append(col_of[key])
        texts.append(rec.get("description") or "")
    m = sp.csr_matrix((np.ones(len(ri)), (ri, ci)), shape=(len(rows), len(col_of)))
    m.data[:] = 1.0
    return m, texts


def embed(texts: list[str], params: dict) -> np.ndarray:
    """Description embeddings (cached by vectorize._embed). Blank text = zero row."""
    vectors = np.asarray(_embed(texts, params), dtype=np.float32)
    blank = np.array([not t.strip() for t in texts])
    vectors[blank] = 0.0
    return vectors


# ---------------------------------------------------------------------------
# building
# ---------------------------------------------------------------------------

def build(cfg: dict, db_path: Path = DB_PATH) -> dict:
    t0 = time.time()
    tcfg = cfg["translation"]
    params = vectorization_params(cfg)
    k = cfg["layout"]["neighbor_count"]

    base_version, base, clusters = read_base_map(REPO_ROOT / tcfg["base_map_db"])
    if base_version != tcfg["base_map_version"]:
        raise SystemExit(f"{tcfg['base_map_db']} holds map {base_version}, the config expects "
                         f"{tcfg['base_map_version']}. Nothing was built.")

    # --- 1. v3 vectors, the same way build_map makes them ---
    weighted = {c for c, w in cfg["category_weights"].items() if w}
    corpus = load_corpus(db_path, alias_lookup(cfg), cfg["vectorization"]["text_field"],
                         only_with_votes=True, feature_categories=weighted)
    vectors = vectorize(corpus, cfg["vectorization"]["method"], params).astype(np.float32)
    on_v3 = np.array([g in base for g in corpus.game_ids])
    pool_ids = corpus.game_ids[on_v3]
    pool = vectors[on_v3]
    pool_xy = np.array([base[g][:2] for g in pool_ids], dtype=np.float64)
    pool_cluster = np.array([base[g][2] for g in pool_ids])
    say(f"v3 space rebuilt: {len(pool_ids):,} v3 games with votes", t0)

    games = read_games(db_path)
    dropped_v3 = sorted(g for g in base if g not in games["row_of"])          # folded duplicate apps
    voted_not_on_v3 = int((~on_v3).sum())

    # --- 2. train on merged v3 games ---
    pool_rows = np.array([games["row_of"][g] for g in pool_ids])
    is_train = np.array([games["raw_igdb"][i] is not None and games["source"][i] == "steam" for i in pool_rows])
    train_rows = pool_rows[is_train]
    train_features, train_texts = igdb_view(games, train_rows, cfg)
    train_text = embed(train_texts, params)
    translator = Translator(tcfg["ridge_lambda"], tcfg["min_feature_games"]).fit(
        train_features, train_text, pool[is_train])
    say(f"translator trained on {len(train_rows):,} merged games "
        f"({len(translator.columns):,} feature columns + {train_text.shape[1]} text dims)", t0)

    # --- 3. translate every game without votes ---
    # (Steam games with votes that are somehow not on v3 would also need a
    # spot. There are none today; the summary counts them.)
    new_rows = np.flatnonzero(~games["has_votes"])
    new_ids = games["game_id"][new_rows]
    new_text = embed([games["description"][i] for i in new_rows], params)
    new_features = games["features"][new_rows]
    translated = translator.predict(new_features, new_text)
    has_vector = np.linalg.norm(translated, axis=1) > 0
    say(f"translated {len(new_rows):,} games without votes ({int((~has_vector).sum()):,} had nothing to translate)", t0)

    # --- 4. recommendations by CSLS (only games that could be translated) ---
    hubs = hub_scores(pool, translated[has_vector], tcfg["csls_k"])
    rec_idx = np.zeros((len(new_rows), k), dtype=np.int64)
    rec_cos = np.zeros((len(new_rows), k))
    confidence = np.zeros(len(new_rows))
    idx, cos, best = csls_topk(translated[has_vector], pool, pool_ids, hubs, k)
    rec_idx[has_vector], rec_cos[has_vector], confidence[has_vector] = idx, cos, best
    say("recommendations ranked", t0)

    # --- the map gate ---
    gate_cfg = tcfg["map_gate"]
    n_features = np.asarray((new_features > 0).sum(axis=1)).ravel()
    has_text = np.abs(new_text).sum(axis=1) > 0
    gate = has_vector & (games["non_game"][new_rows] == 0) & (n_features >= gate_cfg["min_features"])
    if gate_cfg.get("require_description"):
        gate &= has_text
    if gate_cfg.get("min_confidence") is not None:
        gate &= confidence >= gate_cfg["min_confidence"]

    # --- 5. placement ---
    pl = tcfg["placement"]
    g_rows = np.flatnonzero(gate)
    targets = group_targets(pool_xy[rec_idx[g_rows]], rec_cos[g_rows], pl["group_radius"], pl["similarity_power"])
    placed = spread_out(pool_xy, targets, new_ids[g_rows], pl)
    colour = colour_from_map(pool_xy, pool_cluster, placed, pl["colour_neighbors"], len(clusters))
    say(f"placed {len(g_rows):,} new games on the map", t0)

    # --- rows for publish.py ---
    positions = [{"game_id": int(g), "x": float(x), "y": float(y), "cluster_id": int(c),
                  "placement": "v3", "confidence": None}
                 for g, (x, y), c in zip(pool_ids, pool_xy, pool_cluster)]
    positions += [{"game_id": int(new_ids[i]), "x": round(float(p[0]), 6), "y": round(float(p[1]), 6),
                   "cluster_id": int(c), "placement": "translated", "confidence": round(float(confidence[i]), 6)}
                  for i, p, c in zip(g_rows, placed, colour)]
    neighbors = nearest_neighbors(pool, pool_ids, k)          # v3 games: their own v3 lists
    for i in g_rows:
        for rank, (j, s) in enumerate(zip(rec_idx[i], rec_cos[i]), start=1):
            neighbors.append({"game_id": int(new_ids[i]), "neighbor_game_id": int(pool_ids[j]),
                              "similarity_score": round(float(s), 6), "rank": rank})
    say(f"{len(positions):,} map rows, {len(neighbors):,} neighbour rows", t0)

    return {
        "clusters": clusters, "positions": positions, "neighbors": neighbors,
        "stats": {
            "base_map": base_version, "v3_games_kept": len(pool_ids), "v3_games_dropped_folded": dropped_v3,
            "voted_games_not_on_v3": voted_not_on_v3, "training_games": len(train_rows),
            "feature_columns": len(translator.columns), "games_without_votes": len(new_rows),
            "untranslatable": int((~has_vector).sum()),
            "gate": {"passed": int(gate.sum()),
                     "igdb": int((gate & (games["source"][new_rows] == "igdb")).sum()),
                     "steam": int((gate & (games["source"][new_rows] == "steam")).sum()),
                     "failed_non_game": int((games["non_game"][new_rows] == 1).sum()),
                     "failed_few_features": int((has_vector & (n_features < gate_cfg["min_features"])).sum()),
                     "failed_no_description": int((has_vector & ~has_text).sum())},
            "confidence_of_map_games": {q: round(float(np.percentile(confidence[gate], q)), 3) for q in (10, 50, 90)},
            "busiest_v3_game_top1": int(np.bincount(rec_idx[gate][:, 0], minlength=len(pool)).max()),
            "v3_games_used_as_recs": round(float(np.mean(np.bincount(rec_idx[gate].ravel(), minlength=len(pool)) > 0)), 4),
            "seconds": round(time.time() - t0),
        },
        "_arrays": {"pool_xy": pool_xy, "pool_cluster": pool_cluster, "placed": placed, "colour": colour,
                    "rec_idx": rec_idx[g_rows]},
    }


def map_checks(result: dict) -> dict:
    """The look-and-feel numbers from docs/map-v4.md, measured on this build."""
    from scipy.spatial import cKDTree

    a = result["_arrays"]
    xy, cl, placed, colour, rec = a["pool_xy"], a["pool_cluster"], a["placed"], a["colour"], a["rec_idx"]
    tree = cKDTree(xy)
    _, near = tree.query(placed, k=15)
    everything = np.vstack([xy, placed])
    gap = cKDTree(everything).query(placed, k=2)[0][:, 1]
    rec_d = np.linalg.norm(xy[rec[:, :5]] - placed[:, None, :], axis=2)
    _, near_v3 = tree.query(xy, k=16)
    return {
        "colour_matches_surroundings": round(float(np.mean(cl[near] == colour[:, None])), 4),
        "v3_colour_matches_surroundings": round(float(np.mean(cl[near_v3[:, 1:]] == cl[:, None])), 4),
        "stranded_over_50_units": round(float(np.mean(tree.query(placed, k=1)[0] > 50)), 5),
        "on_top_of_another_point": round(float(np.mean(gap < 0.2)), 5),
        "top5_recs_within_25_units": round(float(np.mean(rec_d < 25)), 4),
    }


def fingerprint(result: dict) -> str:
    """One hash of everything that would be published, for the two-builds check (REL 2)."""
    h = hashlib.sha256()
    h.update(json.dumps(result["clusters"], sort_keys=True).encode())
    for key in ("positions", "neighbors"):
        for row in result[key]:                   # row by row, so no giant string is built
            h.update(repr(sorted(row.items())).encode())
    return h.hexdigest()


def write_report(result: dict, checks: dict, digest: str, version: str) -> None:
    s = result["stats"]
    lines = [f"# Map {version} build report", "",
             f"Built by `python -m pipeline.build_map_v4`. Map {s['base_map']} is kept as published; the reasons "
             "for every step are in docs/map-v4.md.", "",
             "| | |", "|---|---|",
             f"| v3 games kept (same x, y, cluster) | {s['v3_games_kept']:,} |",
             f"| v3 games dropped (folded duplicate apps, no games row) | {len(s['v3_games_dropped_folded'])} |",
             f"| Steam games with votes not on v3 | {s['voted_games_not_on_v3']} |",
             f"| translator training games | {s['training_games']:,} ({s['feature_columns']:,} feature columns) |",
             f"| games without votes | {s['games_without_votes']:,} |",
             f"| ... nothing to translate | {s['untranslatable']:,} |",
             f"| ... on the map (gate) | {s['gate']['passed']:,} (IGDB {s['gate']['igdb']:,}, Steam {s['gate']['steam']:,}) |",
             f"| ... left off: not a game / under 3 features / no description | {s['gate']['failed_non_game']:,} / "
             f"{s['gate']['failed_few_features']:,} / {s['gate']['failed_no_description']:,} |",
             f"| total map games | {len(result['positions']):,} |",
             f"| neighbour rows | {len(result['neighbors']):,} |",
             f"| confidence of map games (10th / median / 90th pct) | {s['confidence_of_map_games']} |",
             f"| busiest v3 game as a #1 recommendation | {s['busiest_v3_game_top1']:,} new games |",
             f"| v3 games used as a recommendation | {s['v3_games_used_as_recs']:.1%} |",
             f"| colour matches the 15 v3 points around it | {checks['colour_matches_surroundings']:.1%} "
             f"(v3 games: {checks['v3_colour_matches_surroundings']:.1%}) |",
             f"| stranded more than 50 units from any v3 game | {checks['stranded_over_50_units']:.2%} |",
             f"| within 0.2 units of another point | {checks['on_top_of_another_point']:.2%} |",
             f"| top-5 recommendations within 25 units | {checks['top5_recs_within_25_units']:.1%} |",
             f"| build time | {s['seconds']:,} s |",
             f"| fingerprint (two builds must match) | `{digest[:16]}` |", ""]
    if s["v3_games_dropped_folded"]:
        lines += ["Dropped v3 game ids (each was a duplicate Steam app, now folded into another game): "
                  + ", ".join(str(g) for g in s["v3_games_dropped_folded"]), ""]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--publish", action="store_true", help="write v4 into data/games.db and export data/map_v4.db")
    parser.add_argument("--export-to", type=Path, default=V4_MAP_DB, help="browser database to write (never data/map.db by default)")
    args = parser.parse_args(argv)

    cfg = load_config()
    tcfg = cfg["translation"]
    version = tcfg["map_version"]
    if not is_valid_version_id(version):
        sys.exit(f"translation.map_version {version!r} is not a valid version id")
    if args.publish and cfg["vectorization"]["embedding_device"] != "cpu":
        sys.exit("published maps are CPU-built (REL 2). Set vectorization.embedding_device to cpu.")

    result = build(cfg)
    with sqlite3.connect(DB_PATH.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        known = {g for (g,) in conn.execute("SELECT game_id FROM games")}
    publish.validate(result["clusters"], result["positions"], result["neighbors"],
                     known, max_games=tcfg["max_map_games"])
    for p in result["positions"]:
        if p["placement"] not in ("v3", "translated"):
            sys.exit(f"game {p['game_id']} has placement {p['placement']!r}")
    checks = map_checks(result)
    digest = fingerprint(result)
    write_report(result, checks, digest, version)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS_DIR / f"map_{version}_summary.json").write_text(
        json.dumps({"stats": result["stats"], "checks": checks, "fingerprint": digest}, indent=2), encoding="utf-8")
    print(json.dumps({"checks": checks, "fingerprint": digest[:16]}, indent=2))
    print(f"validate: ok. Report: {REPORT_PATH.relative_to(REPO_ROOT)}")

    if args.publish:
        if args.export_to.resolve() == (REPO_ROOT / "data" / "map.db").resolve():
            sys.exit("refusing to overwrite data/map.db, the live v3 map. Switching the site to v4 is a reviewed step.")
        publish.publish_map(version, result["clusters"], result["positions"], result["neighbors"],
                            dataset_hash=digest, config_snapshot={**cfg, "map_version": version},
                            feature_artifact_ref="translation:ridge+csls", max_games=tcfg["max_map_games"])
        print(f"published {version} into {DB_PATH.name}")
        export_map_db(DB_PATH, args.export_to)
        print(f"exported {args.export_to}")
    else:
        print("dry run: nothing written to the database (use --publish)")


if __name__ == "__main__":
    main()
