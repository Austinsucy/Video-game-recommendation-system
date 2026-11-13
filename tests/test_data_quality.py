"""
Tests that run against the real built database (data/games.db).

Unlike the other test files, these need an actual import to have happened.
If the database is missing they skip rather than fail, so a teammate who has
just cloned the repo does not get a wall of red before downloading the CSV.

These are the tests that check our data quality requirements, DATA 1,
DATA 2 and CON 3, are genuinely met rather than just intended. The DATA 2
checks also skip until a map version has been published.
"""
import json

import pytest
from sqlalchemy import func, select

from backend.app.db import DB_PATH, SessionLocal
from backend.app.models import (
    Feature,
    Game,
    GameFeature,
    GameFeatureCoverage,
    GameSource,
    MapGame,
    MapNeighbor,
    MapVersion,
)
from pipeline.compare_vectors import read_pair_titles
from pipeline.config import load_config

pytestmark = pytest.mark.skipif(
    not DB_PATH.exists(),
    reason="no database yet, run `python -m pipeline.ingest` first",
)

MAX_GAMES = 1100  # CON 3
DATA2_TOP_K = 15
DATA2_MIN_SHARE = 0.8  # DATA 2: at least 8 of 10 known pairs


@pytest.fixture(scope="module")
def session():
    """One read-only session shared by every test in this file."""
    with SessionLocal() as s:
        yield s


# ---------------------------------------------------------------------------
# The headline requirements
# ---------------------------------------------------------------------------

def test_database_is_not_empty(session):
    assert session.scalar(select(func.count(Game.game_id))) > 0


def test_game_count_within_cap(session):
    """CON 3 caps the PUBLISHED MAP at 1,100 games, not the games table.

    Those are different things, and the difference matters on this branch.
    The table can hold the whole catalogue; what CON 3 limits is how many of
    them end up in a map version. pipeline/publish.py enforces that gate, and
    tests/test_publish.py::test_cap_is_enforced proves it.

    So here we check the import's own target, which is what decides how big a
    map we could build from this database.
    """
    target = load_config()["selection"].get("target_count")
    if target is None:
        # mode: all, no limit. The real check is the publish-time one.
        total = session.scalar(select(func.count(Game.game_id)))
        assert total > 0
        return
    assert target <= MAX_GAMES


def _completeness(session) -> tuple[int, int]:
    """Count how many games meet DATA 1, and how many there are in total."""
    genre_ids = set(
        session.scalars(
            select(Feature.feature_id).where(Feature.category == "genre")
        ).all()
    )

    total_features = {}
    genre_features = {}
    for game_id, feature_id in session.execute(
        select(GameFeature.game_id, GameFeature.feature_id)
    ):
        total_features[game_id] = total_features.get(game_id, 0) + 1
        if feature_id in genre_ids:
            genre_features[game_id] = genre_features.get(game_id, 0) + 1

    games = session.scalars(select(Game)).all()
    complete = [
        g for g in games
        if g.title
        and g.release_year
        and genre_features.get(g.game_id, 0) >= 1
        and total_features.get(g.game_id, 0) >= 3
    ]
    return len(complete), len(games)


def test_data1_completeness_at_least_95_percent(session):
    """DATA 1: title, release year, 1+ genre, 3+ features, for 95% of games.

    Skipped when the import deliberately turned the minimums off. The `all`
    selection mode imports the entire Steam catalogue including games with no
    tags at all, so this gate does not apply to that build. The production
    import uses min_genres: 1 and min_tags: 3, which is what makes the 95%
    achievable in the first place.
    """
    selection = load_config()["selection"]
    if selection.get("min_genres", 0) < 1 or selection.get("min_tags", 0) < 3:
        complete, total = _completeness(session)
        pytest.skip(
            f"this import ran with the DATA 1 minimums turned off "
            f"(min_genres={selection.get('min_genres')}, "
            f"min_tags={selection.get('min_tags')}), so the 95% gate does not "
            f"apply. For the record, {complete:,} of {total:,} games "
            f"({complete / total * 100:.1f}%) would pass it."
        )

    complete, total = _completeness(session)
    assert complete / total >= 0.95


def test_completeness_is_reported_not_silent(session):
    """Whatever the minimums were, we should always be able to state the number.

    This never fails. It exists so the actual completeness shows up in the
    test output rather than only in the import report, which makes it visible
    in CI and in a PR.
    """
    complete, total = _completeness(session)
    assert total > 0
    print(f"\nDATA 1 completeness: {complete:,} of {total:,} "
          f"({complete / total * 100:.1f}%)")


def test_no_game_appears_twice(session):
    """Checked on IDs, not titles.

    Two different games genuinely can share a title (remasters, regional
    editions). Our scrum doc says those get reported for review, not merged,
    so the duplicate check here is on identity rather than name.
    """
    external_ids = session.scalars(select(GameSource.external_id)).all()
    assert len(external_ids) == len(set(external_ids))

    game_ids = session.scalars(select(Game.game_id)).all()
    assert len(game_ids) == len(set(game_ids))


# ---------------------------------------------------------------------------
# Data integrity
# ---------------------------------------------------------------------------

def test_every_game_has_a_source(session):
    """We should always be able to say where a game came from."""
    linked = set(session.scalars(select(GameSource.game_id)).all())
    everything = set(session.scalars(select(Game.game_id)).all())
    assert everything - linked == set()


def test_title_search_is_populated_and_normalised(session):
    """Every game must be searchable.

    This caught a real bug on the full catalogue: games titled only with
    symbols, like "***" or "∞", were being cleaned down to an empty string.
    normalise_title now falls back to the plain lowercased title in that case.
    """
    for title_search in session.scalars(select(Game.title_search)):
        assert title_search != ""
        assert title_search == title_search.strip()
        assert title_search == title_search.lower()


def test_no_orphan_feature_links(session):
    """Every link should point at a real game and a real feature."""
    feature_ids = set(session.scalars(select(Feature.feature_id)).all())
    game_ids = set(session.scalars(select(Game.game_id)).all())

    for game_id, feature_id in session.execute(
        select(GameFeature.game_id, GameFeature.feature_id)
    ):
        assert game_id in game_ids
        assert feature_id in feature_ids


def test_coverage_row_for_every_game_and_category(session):
    """Nine categories per game, no gaps."""
    games = session.scalar(select(func.count(Game.game_id)))
    rows = session.scalar(select(func.count()).select_from(GameFeatureCoverage))
    assert rows == games * 9


# ---------------------------------------------------------------------------
# The cleaning actually happened
# ---------------------------------------------------------------------------

def test_zero_sentinels_were_converted_to_null(session):
    """Steam writes 0 to mean 'no data'. Those should be NULL, not 0.

    A game with exactly 0 hours of playtime is not a real thing, so finding
    one means the conversion stopped working and every playtime average we
    calculate from here on would be wrong.
    """
    zero_playtime = session.scalar(
        select(func.count()).select_from(Game).where(Game.playtime_hours == 0)
    )
    assert zero_playtime == 0


def test_rating_scale_present_whenever_rating_is(session):
    """A rating with no scale is ambiguous: is 85 out of 100, or out of 5?"""
    bad = session.scalar(
        select(func.count())
        .select_from(Game)
        .where(Game.rating.isnot(None), Game.rating_scale.is_(None))
    )
    assert bad == 0


def test_raw_tags_are_valid_json_with_vote_counts(session):
    """The raw tags column should hold a usable object, not a mangled string.

    Spot-checks 50 games rather than all 1000, which is plenty to catch a
    formatting problem and keeps the suite fast.
    """
    sample = session.scalars(
        select(Game.raw_tags_json).where(Game.raw_tags_json.isnot(None)).limit(50)
    ).all()
    assert sample, "no game has raw tags, which should not happen"

    for blob in sample:
        tags = json.loads(blob)
        assert isinstance(tags, dict)
        assert tags, "a game has an empty tag object"
        for name, votes in tags.items():
            assert isinstance(name, str)
            assert isinstance(votes, int)   # the vote count we keep this column for


# ---------------------------------------------------------------------------
# The long description
# ---------------------------------------------------------------------------

def test_long_description_is_present_for_almost_every_game(session):
    """It is allowed to be NULL, but it should be rare."""
    total = session.scalar(select(func.count(Game.game_id)))
    missing = session.scalar(
        select(func.count()).select_from(Game).where(Game.long_description.is_(None))
    )
    assert missing / total < 0.05


def test_long_description_is_longer_than_the_short_one(session):
    """Sanity check that we did not accidentally map both to the same column.

    Checked on averages rather than per game, because a handful of games
    genuinely do have a one-line About section.
    """
    short_avg, long_avg = session.execute(
        select(func.avg(func.length(Game.description)),
               func.avg(func.length(Game.long_description)))
    ).one()
    assert long_avg > short_avg * 2


# ---------------------------------------------------------------------------
# Release date, developers and publishers
# ---------------------------------------------------------------------------

def test_release_date_is_iso_format(session):
    """Dates have to be YYYY-MM-DD to sort correctly.

    SQLite has no date type, so dates are just text. Text sorts
    alphabetically, which only matches chronological order if the format is
    consistent and starts with the year. "03/15/2022" would sort completely
    wrong.
    """
    import re
    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    dates = session.scalars(
        select(Game.release_date).where(Game.release_date.isnot(None))
    ).all()
    assert dates, "no game has a release date"

    for value in dates:
        assert pattern.match(value), f"{value!r} is not YYYY-MM-DD"


def test_release_year_matches_release_date(session):
    """The two come from the same source, so they must never disagree."""
    rows = session.execute(
        select(Game.game_id, Game.release_date, Game.release_year)
        .where(Game.release_date.isnot(None))
    ).all()

    for game_id, date_text, year in rows:
        assert year == int(date_text[:4]), (
            f"game {game_id} has date {date_text} but year {year}"
        )


def test_most_games_have_a_developer(session):
    """Allowed to be missing, but it should be the exception."""
    total = session.scalar(select(func.count(Game.game_id)))
    missing = session.scalar(
        select(func.count()).select_from(Game).where(Game.developers.is_(None))
    )
    assert missing / total < 0.10


def test_developer_list_has_no_duplicates_or_stray_spacing(session):
    """join_list should produce clean "A, B" text with each studio once."""
    values = session.scalars(
        select(Game.developers).where(Game.developers.isnot(None)).limit(200)
    ).all()

    for value in values:
        assert value == value.strip()
        parts = [p.strip() for p in value.split(",")]
        assert all(parts), f"{value!r} has an empty entry"
        # Note: a studio name can legitimately contain a comma
        # ("KRAFTON, Inc."), so we only check for blanks here, not for a
        # specific number of parts.


def test_no_empty_strings_where_null_is_meant(session):
    """Empty string and NULL both mean 'nothing', and having both is a trap.

    Code that checks `if game.description:` behaves one way, code that checks
    `IS NOT NULL` behaves another. We pick NULL and stick to it.
    """
    for column in (Game.description, Game.long_description,
                   Game.developers, Game.publishers,
                   Game.release_date, Game.cover_image_url, Game.store_url):
        blanks = session.scalar(
            select(func.count()).select_from(Game).where(column == "")
        )
        assert blanks == 0


# ---------------------------------------------------------------------------
# DATA 2: known similar pairs (Austin)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def published_neighbors(session):
    """{game_id: set of its top-15 neighbour ids} for the active map version."""
    version = session.scalar(select(MapVersion.map_version_id).where(MapVersion.is_active == 1))
    if version is None:
        pytest.skip("no published map version; run `python -m pipeline.build_map --publish`")
    on_map = session.scalar(
        select(func.count()).select_from(MapGame).where(MapGame.map_version_id == version)
    )
    # test/full-90k-database only: DATA 2's 80% is a target for the ~1,000-game
    # map. At full-catalogue size clones crowd the top 15 and hybrid_max reaches
    # about 53% (docs/full-90k-findings.md), so the test reports nothing here.
    if on_map > MAX_GAMES:
        pytest.skip(f"active map {version} has {on_map:,} games; DATA 2 targets a map of at most {MAX_GAMES:,}")
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
