"""
Tests for a published map v4 (python -m pipeline.build_map_v4 --publish).

They skip until v4 exists in data/games.db. They check the promises in
docs/map-v4.md: v3 kept exactly, new games labelled and placed sensibly,
recommendations only pointing at v3 games, and the held-out check passing.
"""
import json
import sqlite3

import numpy as np
import pytest
from scipy.spatial import cKDTree

from backend.app.db import DB_PATH
from pipeline.config import ARTIFACTS_DIR, REPO_ROOT, load_config

CFG = load_config()
V4 = CFG["translation"]["map_version"]
BASE = REPO_ROOT / CFG["translation"]["base_map_db"]


def _has_v4() -> bool:
    if not DB_PATH.exists():
        return False
    with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as conn:
        try:
            return bool(conn.execute("SELECT 1 FROM map_versions WHERE map_version_id = ?", (V4,)).fetchone())
        except sqlite3.OperationalError:
            return False


pytestmark = pytest.mark.skipif(not _has_v4(), reason="map v4 not built; run python -m pipeline.build_map_v4 --publish")


@pytest.fixture(scope="module")
def db():
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def maps(db):
    rows = db.execute("SELECT game_id, x, y, cluster_id, placement, confidence FROM map_games "
                      "WHERE map_version_id = ? ORDER BY game_id", (V4,)).fetchall()
    v3 = {g: (x, y, c) for g, x, y, c in sqlite3.connect(f"file:{BASE}?mode=ro", uri=True)
          .execute("SELECT game_id, x, y, cluster_id FROM games")}
    return rows, v3


def test_every_v3_game_keeps_its_spot_and_colour(maps, db):
    rows, v3 = maps
    kept = {g: (x, y, c) for g, x, y, c, p, _ in rows if p == "v3"}
    existing = {g for (g,) in db.execute("SELECT game_id FROM games")}
    assert set(kept) == {g for g in v3 if g in existing}
    for g, value in kept.items():
        assert value == v3[g], g


def test_translated_games_are_labelled_with_a_confidence(maps):
    rows, v3 = maps
    for g, _, _, _, placement, confidence in rows:
        if placement == "translated":
            assert g not in v3 and confidence is not None and 0 < confidence <= 1.0
        else:
            assert placement == "v3" and confidence is None


def test_new_games_recommend_only_v3_games(db):
    bad = db.execute(
        "SELECT COUNT(*) FROM map_neighbors n JOIN map_games src ON src.map_version_id = n.map_version_id "
        "AND src.game_id = n.game_id JOIN map_games dst ON dst.map_version_id = n.map_version_id "
        "AND dst.game_id = n.neighbor_game_id WHERE n.map_version_id = ? AND dst.placement != 'v3'", (V4,)).fetchone()[0]
    assert bad == 0


def test_every_map_game_has_fifteen_neighbours(db):
    counts = db.execute("SELECT COUNT(*) FROM map_neighbors WHERE map_version_id = ? GROUP BY game_id", (V4,)).fetchall()
    total = db.execute("SELECT COUNT(*) FROM map_games WHERE map_version_id = ?", (V4,)).fetchone()[0]
    assert len(counts) == total and {c for (c,) in counts} == {15}


def test_no_non_game_is_added_to_the_map(db):
    # Non-games that were already on v3 (tagged Steam demos and soundtracks)
    # stay where v3 put them; v4 just never ADDS one.
    assert db.execute("SELECT COUNT(*) FROM map_games m JOIN games g USING (game_id) "
                      "WHERE m.map_version_id = ? AND m.placement = 'translated' AND g.is_non_game = 1",
                      (V4,)).fetchone()[0] == 0


def test_new_games_sit_in_the_map_not_in_empty_space(maps):
    rows, _ = maps
    xy = np.array([(x, y) for _, x, y, _, p, _ in rows if p == "v3"])
    new = np.array([(x, y) for _, x, y, _, p, _ in rows if p == "translated"])
    far = cKDTree(xy).query(new, k=1)[0]
    assert np.mean(far > 50) == 0
    # v3 itself stacks games almost on top of each other (about 12% are within
    # 0.2 units of another v3 game, mostly near-identical games), so the rule
    # is "no more stacked than v3", not a fixed number.
    gap = cKDTree(np.vstack([xy, new])).query(new, k=2)[0][:, 1]
    v3_gap = cKDTree(xy).query(xy, k=2)[0][:, 1]
    assert np.mean(gap < 0.2) <= np.mean(v3_gap < 0.2)


def test_new_dots_match_the_colour_around_them(maps):
    rows, _ = maps
    xy = np.array([(x, y) for _, x, y, _, p, _ in rows if p == "v3"])
    cl = np.array([c for _, _, _, c, p, _ in rows if p == "v3"])
    new = np.array([(x, y) for _, x, y, _, p, _ in rows if p == "translated"])
    new_cl = np.array([c for _, _, _, c, p, _ in rows if p == "translated"])
    _, near = cKDTree(xy).query(new, k=15)
    assert np.mean(cl[near] == new_cl[:, None]) >= 0.80


def test_held_out_check_passed():
    path = ARTIFACTS_DIR / "translation_eval.json"
    if not path.exists():
        pytest.skip("run python -m pipeline.eval_translation first")
    result = json.loads(path.read_text())
    ev = CFG["translation"]["evaluation"]
    assert result["ridge_quality"] >= ev["min_quality"]
    assert result["gain_over_text"] >= ev["min_gain_over_text"]
