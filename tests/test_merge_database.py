"""
Tests that run against the real merged database (Steam + IGDB).

Like test_data_quality.py these need a built data/games.db, and they skip
when it is missing. They also skip when the database was built with
--steam-only, because then there is no merge to check.

What they check, in the order the merge prompt lists them:
  parity    every game is stored the same way, whichever source it came from
  folding   Steam's duplicate apps became one game each
  rescue    untagged Steam games got IGDB features, never fake vote counts
  safety    Steam games keep their ids and values
"""
import json
import re
import sqlite3

import pytest

from backend.app.db import DB_PATH
from pipeline.cleaning import clean_display_title, compile_patterns, non_game_match
from pipeline.config import REPO_ROOT, load_config

CFG = load_config()
STEAM = CFG["dataset"]["source_name"]
IGDB = CFG["sources"]["igdb"]["source_name"]


def _has_merge() -> bool:
    if not DB_PATH.exists():
        return False
    with sqlite3.connect(DB_PATH) as conn:
        try:
            return bool(conn.execute(
                "SELECT 1 FROM game_sources WHERE source_name = ? LIMIT 1", (IGDB,)).fetchone())
        except sqlite3.OperationalError:
            return False


pytestmark = pytest.mark.skipif(
    not _has_merge(),
    reason="no merged database, run `python -m pipeline.ingest --reset` with IGDB in data/raw/",
)


@pytest.fixture(scope="module")
def db():
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    yield conn
    conn.close()


def one(db, sql, *args):
    return db.execute(sql, args).fetchone()[0]


def game_for_app(db, appid: int) -> int:
    return one(db, "SELECT game_id FROM game_sources WHERE source_name = ? AND external_id = ?",
               STEAM, str(appid))


# ---------------------------------------------------------------------------
# Parity: the same shape whatever the source
# ---------------------------------------------------------------------------

def test_both_sources_are_present(db):
    by_source = dict(db.execute("SELECT primary_source, COUNT(*) FROM games GROUP BY 1"))
    assert by_source.get("steam", 0) > 80000
    assert by_source.get("igdb", 0) > 100000


def test_release_dates_are_iso_for_every_source(db):
    bad = one(db, "SELECT COUNT(*) FROM games WHERE release_date IS NOT NULL "
                  "AND release_date NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'")
    assert bad == 0
    mismatch = one(db, "SELECT COUNT(*) FROM games WHERE release_date IS NOT NULL "
                       "AND CAST(substr(release_date, 1, 4) AS INTEGER) != release_year")
    assert mismatch == 0


def test_null_not_empty_string_in_any_text_column(db):
    columns = [row[1] for row in db.execute("PRAGMA table_info(games)") if row[2] in ("VARCHAR", "TEXT")]
    assert "header_image_url" in columns and "raw_igdb_json" in columns
    for column in columns:
        assert one(db, f'SELECT COUNT(*) FROM games WHERE TRIM("{column}") = \'\'') == 0, column


def test_every_rating_says_what_kind_of_rating_it_is(db):
    assert one(db, "SELECT COUNT(*) FROM games WHERE rating IS NOT NULL "
                   "AND (rating_kind IS NULL OR rating_scale IS NULL)") == 0
    assert one(db, "SELECT COUNT(*) FROM games WHERE rating IS NULL AND rating_kind IS NOT NULL") == 0
    # And the kind matches where the rating really came from.
    assert one(db, "SELECT COUNT(*) FROM games WHERE primary_source = 'igdb' "
                   "AND rating_kind = 'steam_positive_pct'") == 0


def test_every_game_has_a_source_row(db):
    assert one(db, "SELECT COUNT(*) FROM games WHERE game_id NOT IN (SELECT game_id FROM game_sources)") == 0


def test_every_game_has_nine_coverage_rows(db):
    assert one(db, "SELECT COUNT(*) FROM (SELECT game_id FROM game_feature_coverage "
                   "GROUP BY game_id HAVING COUNT(*) != 9)") == 0
    assert one(db, "SELECT COUNT(*) FROM game_feature_coverage") == one(db, "SELECT COUNT(*) FROM games") * 9


def test_every_feature_link_says_where_it_came_from(db):
    sources = {row[0] for row in db.execute("SELECT DISTINCT source FROM game_features")}
    assert sources <= {"steam", "igdb", "derived_text"}
    assert "igdb" in sources


def test_no_external_id_appears_twice_within_a_source(db):
    assert one(db, "SELECT COUNT(*) FROM (SELECT source_name, external_id FROM game_sources "
                   "GROUP BY 1, 2 HAVING COUNT(*) > 1)") == 0


def test_one_igdb_game_never_lands_on_two_games(db):
    """And one Steam game never gets two IGDB merges."""
    assert one(db, "SELECT COUNT(*) FROM (SELECT game_id FROM game_sources WHERE source_name = ? "
                   "GROUP BY game_id HAVING COUNT(*) > 1)", IGDB) == 0


def test_genre_for_95_percent_of_data1_games_per_source(db):
    """Of the games with a title, a year and 3+ features, 95% also have a genre."""
    rows = db.execute(
        "WITH f AS (SELECT gf.game_id, COUNT(*) AS n, SUM(ft.category = 'genre') AS g "
        "FROM game_features gf JOIN features ft USING (feature_id) GROUP BY gf.game_id) "
        "SELECT g.primary_source, COUNT(*), SUM(f.g >= 1) FROM games g JOIN f USING (game_id) "
        "WHERE g.release_year IS NOT NULL AND f.n >= 3 GROUP BY 1").fetchall()
    for source, total, with_genre in rows:
        assert with_genre / total >= 0.95, f"{source}: {with_genre} of {total}"


def test_igdb_games_never_get_steam_only_columns(db):
    assert one(db, "SELECT COUNT(*) FROM games WHERE primary_source = 'igdb' AND "
                   "(store_url IS NOT NULL OR playtime_hours IS NOT NULL OR rating_count IS NOT NULL "
                   "OR popularity IS NOT NULL OR raw_tags_json IS NOT NULL)") == 0


def test_platform_features_never_come_from_a_substring_match(db):
    """A PC Engine-only game must not have the windows feature."""
    rows = db.execute(
        "SELECT g.game_id, g.platforms_raw FROM games g JOIN game_features gf USING (game_id) "
        "JOIN features f USING (feature_id) WHERE g.primary_source = 'igdb' "
        "AND f.category = 'platform' AND f.name = 'windows'").fetchall()
    for _game_id, platforms in rows:
        assert "PC (Microsoft Windows)" in json.loads(platforms)


# ---------------------------------------------------------------------------
# Folding Steam's own duplicate apps
# ---------------------------------------------------------------------------

def test_ea_sports_fc_25_is_one_game_with_four_steam_rows(db):
    game_id = game_for_app(db, 2669320)
    apps = sorted(int(r[0]) for r in db.execute(
        "SELECT external_id FROM game_sources WHERE source_name = ? AND game_id = ?", (STEAM, game_id)))
    assert apps == [2669320, 2898330, 2898350, 2898360]
    assert one(db, "SELECT COUNT(*) FROM games WHERE title = 'EA SPORTS FC 25'") == 1


def test_metro_exodus_keeps_app_412020_and_its_tags(db):
    game_id = game_for_app(db, 412020)
    assert game_for_app(db, 1449560) == game_id
    raw = json.loads(one(db, "SELECT raw_tags_json FROM games WHERE game_id = ?", game_id))
    assert len(raw) == 20 and all(isinstance(v, int) for v in raw.values())
    method = one(db, "SELECT match_method FROM game_sources WHERE source_name = ? AND external_id = '1449560'", STEAM)
    assert method == "steam_fold"


def test_folded_apps_always_share_their_release_date(db):
    """Same title but a different date is never folded."""
    bad = one(db, "SELECT COUNT(*) FROM (SELECT game_id FROM game_sources WHERE source_name = ? "
                  "GROUP BY game_id HAVING COUNT(DISTINCT release_date_in_source) > 1)", STEAM)
    assert bad == 0


def test_folded_apps_get_no_games_row_of_their_own(db):
    assert one(db, "SELECT COUNT(*) FROM game_sources s WHERE s.match_method = 'steam_fold' "
                   "AND s.game_id NOT IN (SELECT game_id FROM game_sources WHERE match_method = 'steam_primary')") == 0


# ---------------------------------------------------------------------------
# Rescue of the untagged Steam games
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("appid,title", [(2357570, "Overwatch"), (2767030, "Marvel Rivals"),
                                         (2073850, "THE FINALS")])
def test_big_untagged_games_get_igdb_features_and_keep_their_reviews(db, appid, title):
    game_id = game_for_app(db, appid)
    row = db.execute("SELECT title, tag_source, raw_tags_json, raw_tags_kind, rating_count, "
                     "popularity_source FROM games WHERE game_id = ?", (game_id,)).fetchone()
    assert title.lower() in row[0].lower()
    assert row[1] == "igdb" and row[2] is None and row[3] == "presence"
    assert row[4] and row[4] > 10000 and row[5] == "steam_review_count"
    igdb_features = one(db, "SELECT COUNT(*) FROM game_features WHERE game_id = ? AND source = 'igdb'", game_id)
    assert igdb_features >= 3


def test_no_derived_text_features_unless_turned_on(db):
    if CFG["sources"]["igdb"].get("derived_text", {}).get("enabled"):
        pytest.skip("derived_text is turned on in the config")
    assert one(db, "SELECT COUNT(*) FROM game_features WHERE source = 'derived_text'") == 0


def test_no_invented_vote_counts(db):
    """raw_tags_json (tag -> votes) only ever holds Steam's real votes."""
    assert one(db, "SELECT COUNT(*) FROM games WHERE raw_tags_json IS NOT NULL AND "
                   "(tag_source != 'steam_votes' OR raw_tags_kind != 'votes')") == 0
    assert one(db, "SELECT COUNT(*) FROM games WHERE tag_source = 'igdb' AND raw_tags_json IS NOT NULL") == 0


def test_every_non_game_matches_a_configured_pattern(db):
    patterns = compile_patterns(CFG["non_game_patterns"])
    rows = db.execute(
        "SELECT g.title, (SELECT GROUP_CONCAT(s.title_in_source, char(10)) FROM game_sources s "
        "WHERE s.game_id = g.game_id) FROM games g WHERE g.is_non_game = 1").fetchall()
    assert rows, "no non-games flagged at all, the patterns are probably not loading"
    for title, originals in rows:
        names = [title] + (originals or "").split("\n")
        assert any(non_game_match(n, patterns) for n in names), title


# ---------------------------------------------------------------------------
# Steam safety: Steam games keep their ids and values
# ---------------------------------------------------------------------------

STEAM_CSV = REPO_ROOT / CFG["dataset"]["csv_path"]


@pytest.fixture(scope="module")
def steam_selection():
    if not STEAM_CSV.exists():
        pytest.skip("Steam CSV not in data/raw/")
    from pipeline.ingest import select_games
    chosen, _ = select_games(CFG, STEAM_CSV)
    return chosen


def test_every_steam_app_keeps_mains_id(db, steam_selection):
    """main numbers Steam apps 1, 2, 3, ... in selection order. So do we.

    A folded app keeps its own id in the numbering (it just has no games row
    and its game_sources row points at the kept game), so no other Steam game
    moves.
    """
    stored = dict(db.execute("SELECT external_id, game_id FROM game_sources WHERE source_name = ?", (STEAM,)))
    primary = dict(db.execute("SELECT external_id, game_id FROM game_sources WHERE source_name = ? "
                              "AND match_method = 'steam_primary'", (STEAM,)))
    assert len(stored) == len(steam_selection)
    for position, appid in enumerate(steam_selection["appid"].astype(int), start=1):
        if str(appid) in primary:
            assert primary[str(appid)] == position, appid


def test_steam_values_are_unchanged_except_trademark_signs(db, steam_selection):
    rows = {int(r[0]): r[1:] for r in db.execute(
        "SELECT s.external_id, g.title, s.title_in_source, g.rating_count, g.release_date "
        "FROM game_sources s JOIN games g USING (game_id) "
        "WHERE s.source_name = ? AND s.match_method = 'steam_primary'", (STEAM,))}
    for rec in steam_selection[["appid", "name", "num_reviews_total"]].itertuples(index=False):
        if int(rec.appid) not in rows:
            continue
        title, original, rating_count, _date = rows[int(rec.appid)]
        assert original == rec.name
        assert title == clean_display_title(rec.name)
        assert re.sub(r"[™®©℠\s]", "", title) == re.sub(r"[™®©℠\s]", "", rec.name)
        assert rating_count == int(rec.num_reviews_total)
