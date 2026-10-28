"""DATA 1, CON 3 and integrity checks against the built database.

These run against data/games.db, so they are skipped until the import has run.
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
)

pytestmark = pytest.mark.skipif(
    not DB_PATH.exists(), reason="run `python -m pipeline.ingest` first"
)

MAX_GAMES = 1100  # CON 3


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
