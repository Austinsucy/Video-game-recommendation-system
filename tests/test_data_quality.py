"""DATA 1, DATA 2, CON 3 and integrity checks against the built database.

These run against data/games.db, so they are skipped until the import has run.
The DATA 2 checks are also skipped until a map version is published.
"""
import pytest
from sqlalchemy import func, select

from backend.app.db import DB_PATH, SessionLocal
from backend.app.models import (
    Feature,
    Game,
    GameFeature,
    GameFeatureCoverage,
    GameSource,
    MapNeighbor,
    MapVersion,
)
from pipeline.compare_vectors import read_pair_titles

pytestmark = pytest.mark.skipif(
    not DB_PATH.exists(), reason="run `python -m pipeline.ingest` first"
)

MAX_GAMES = 1100  # CON 3
DATA2_TOP_K = 15
DATA2_MIN_SHARE = 0.8  # DATA 2: at least 8 of 10 known pairs


@pytest.fixture(scope="module")
def session():
    with SessionLocal() as s:
        yield s


def test_database_is_not_empty(session):
    assert session.scalar(select(func.count(Game.game_id))) > 0


def test_game_count_within_cap(session):
    assert session.scalar(select(func.count(Game.game_id))) <= MAX_GAMES


def test_data1_completeness_at_least_95_percent(session):
    """Title, release year, at least one genre, at least three features."""
    genre_ids = set(
        session.scalars(
            select(Feature.feature_id).where(Feature.category == "genre")
        ).all()
    )
    totals, genres = {}, {}
    for gid, fid in session.execute(select(GameFeature.game_id, GameFeature.feature_id)):
        totals[gid] = totals.get(gid, 0) + 1
        if fid in genre_ids:
            genres[gid] = genres.get(gid, 0) + 1

    games = session.scalars(select(Game)).all()
    complete = [
        g
        for g in games
        if g.title
        and g.release_year
        and genres.get(g.game_id, 0) >= 1
        and totals.get(g.game_id, 0) >= 3
    ]
    assert len(complete) / len(games) >= 0.95


def test_no_game_appears_twice(session):
    """One row per external id. Duplicate TITLES are reported, not merged."""
    ids = session.scalars(select(GameSource.external_id)).all()
    assert len(ids) == len(set(ids))
    game_ids = session.scalars(select(Game.game_id)).all()
    assert len(game_ids) == len(set(game_ids))


def test_every_game_has_a_source(session):
    linked = set(session.scalars(select(GameSource.game_id)).all())
    allg = set(session.scalars(select(Game.game_id)).all())
    assert allg - linked == set()


def test_title_search_is_populated_and_normalised(session):
    for title_search in session.scalars(select(Game.title_search)):
        assert title_search == title_search.strip()
        assert title_search == title_search.lower()
        assert title_search != ""


def test_no_orphan_feature_links(session):
    feature_ids = set(session.scalars(select(Feature.feature_id)).all())
    game_ids = set(session.scalars(select(Game.game_id)).all())
    for gid, fid in session.execute(select(GameFeature.game_id, GameFeature.feature_id)):
        assert gid in game_ids
        assert fid in feature_ids


def test_coverage_row_for_every_game_and_category(session):
    games = session.scalar(select(func.count(Game.game_id)))
    rows = session.scalar(select(func.count()).select_from(GameFeatureCoverage))
    assert rows == games * 9  # nine approved categories


def test_zero_sentinels_were_converted_to_null(session):
    """Steam writes 0 for 'no data'. A rating of exactly 0 with reviews is fine,
    but playtime of 0 hours must have become NULL."""
    zero_playtime = session.scalar(
        select(func.count()).select_from(Game).where(Game.playtime_hours == 0)
    )
    assert zero_playtime == 0


def test_rating_scale_present_whenever_rating_is(session):
    bad = session.scalar(
        select(func.count())
        .select_from(Game)
        .where(Game.rating.isnot(None), Game.rating_scale.is_(None))
    )
    assert bad == 0


@pytest.fixture(scope="module")
def published_neighbors(session):
    """{game_id: set of its top-15 neighbour ids} for the active map version."""
    version = session.scalar(select(MapVersion.map_version_id).where(MapVersion.is_active == 1))
    if version is None:
        pytest.skip("no published map version; run `python -m pipeline.build_map --publish`")
    neighbors: dict[int, set[int]] = {}
    for gid, nid in session.execute(
        select(MapNeighbor.game_id, MapNeighbor.neighbor_game_id).where(
            MapNeighbor.map_version_id == version, MapNeighbor.rank <= DATA2_TOP_K
        )
    ):
        neighbors.setdefault(gid, set()).add(nid)
    return neighbors


def test_every_similar_pair_names_games_in_the_database(session):
    titles = set(session.scalars(select(Game.title)).all())
    missing = sorted({t for pair in read_pair_titles() for t in pair} - titles)
    assert missing == []


def test_data2_similar_pairs_are_in_each_others_top_15(session, published_neighbors):
    """DATA 2: at least 80% of the approved pairs are mutual top-15 neighbours."""
    game_id = dict(session.execute(select(Game.title, Game.game_id)).all())
    pairs = [(game_id[a], game_id[b]) for a, b in read_pair_titles()]
    mutual = [
        b in published_neighbors.get(a, set()) and a in published_neighbors.get(b, set())
        for a, b in pairs
    ]
    assert sum(mutual) / len(pairs) >= DATA2_MIN_SHARE, f"{sum(mutual)} of {len(pairs)} pairs"
