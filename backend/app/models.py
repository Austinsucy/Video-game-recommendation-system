"""
All of our database tables, written as SQLAlchemy models.

HOW TO READ THIS FILE
---------------------
Each class below is one table. Each `Mapped[...]` line is one column.
`Mapped[str]` means the column cannot be empty. `Mapped[str | None]`
means it is allowed to be empty (NULL).

`__table_args__` at the bottom of a class is where we put the rules that
SQLite itself should enforce, like "this combination has to be unique" or
"this number has to be at least 1". Putting rules here instead of in Python
means they are impossible to break by accident, even if someone writes to
the database from a script we did not plan for.

The table layout comes from our scrum doc, "First Scrum Cycle: Game Database
Structure". Two things are marked ADDITION. Those are tables or columns the
doc did not list, but that we needed in order to follow a rule the doc states.
They are flagged so the team can review them.
"""
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Every model inherits from this. SQLAlchemy uses it to keep track of
    all our tables so `Base.metadata.create_all()` can build them."""


# ===========================================================================
# 1. games - one row per game
# ===========================================================================
class Game(Base):
    __tablename__ = "games"

    # Our own ID, counting up from 1. This is deliberately NOT the Steam
    # app id. If we ever switch data sources, or pull the same game from two
    # places, our ID stays the same and the Steam id lives in game_sources.
    game_id: Mapped[int] = mapped_column(primary_key=True)

    # The name we actually show on screen, exactly as the source spells it.
    title: Mapped[str] = mapped_column(nullable=False)

    # The same name, but lowercased with punctuation removed. We search
    # against this instead of `title` so that typing "witcher 3" still finds
    # "The Witcher 3: Wild Hunt". It is also how we spot likely duplicates.
    title_search: Mapped[str] = mapped_column(nullable=False)

    # We keep both the full date and just the year, on purpose.
    #   release_date  "2022-02-24", for showing the real date in the info panel
    #   release_year  2022, for filtering and for the map, where the day is noise
    # Storing the year separately means we never have to parse a string to
    # answer "which games came out in 2022?", which the selection filter asks
    # on all 89,618 rows.
    release_date: Mapped[str | None]
    release_year: Mapped[int | None]

    # Two different lengths of description, for two different places in the UI.
    #   description      -> the one or two sentence blurb, for the info panel
    #   long_description -> the full "About This Game" text, for when the user
    #                       wants to actually read about it
    # We keep them separate because `description` is small enough to ship in
    # bulk, while long_description averages about 1,400 characters. Sending
    # 1,000 of those at once would be a few megabytes, which is exactly what
    # the PERF 2 requirement tells us not to do.
    description: Mapped[str | None]
    long_description: Mapped[str | None]

    # Who made it and who sold it. Stored as comma-joined text rather than as
    # their own tables, because about 8% of games have more than one developer
    # (one has 41) and we only need to display them, not search or group by them.
    #
    # If we later want "show me everything by FromSoftware", these should
    # become a `companies` table plus a link table, the same shape as features.
    developers: Mapped[str | None]
    publishers: Mapped[str | None]

    cover_image_url: Mapped[str | None]
    store_url: Mapped[str | None]

    # Hours, converted from the source's minutes. See map_config.yaml for
    # which exact Steam playtime number this is, since Steam publishes
    # several and they mean different things.
    playtime_hours: Mapped[float | None]

    # rating is a number, rating_scale says what that number means.
    # Storing the scale alongside the value means nobody has to guess whether
    # 85 is "85 out of 100" or "85 out of 5". If we ever add a second data
    # source that uses a different scale, this still works.
    rating: Mapped[float | None]
    rating_scale: Mapped[str | None]
    rating_count: Mapped[int | None]

    # Used to decide which games get a visible label on the map when things
    # get crowded. Which number this is comes from map_config.yaml.
    popularity: Mapped[float | None]

    # ADDITION (team review)
    # Our import rules say "preserve the original dataset export and raw tags".
    # Nothing else in the schema could hold them: by the time a tag reaches
    # game_features it has been cleaned up and renamed, so the original is gone.
    #
    # This matters more than it sounds, because Steam's tags arrive with vote
    # counts attached, like {"Battle Royale": 1483, "Action": 825}. Those
    # counts tell you how strongly a tag applies. game_features can only say
    # yes or no, so without this column the counts are thrown away forever.
    raw_tags_json: Mapped[str | None]

    # These two let us write `game.sources` and `game.features` in Python
    # instead of writing a JOIN by hand every time.
    sources: Mapped[list["GameSource"]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )
    features: Mapped[list["Feature"]] = relationship(
        secondary="game_features", viewonly=True
    )

    __table_args__ = (
        # Required by our import rules. Without an index, searching means
        # SQLite reads all 1,000 rows every time. With one, it jumps straight
        # to the matches.
        Index("ix_games_title_search", "title_search"),
    )


# ===========================================================================
# 2. game_sources - where each game came from
# ===========================================================================
class GameSource(Base):
    """Records which dataset a game came from and what its ID was over there.

    The primary key is (source_name, external_id) rather than game_id, because
    one of our games could legitimately appear in two different datasets. That
    would be two rows here, both pointing at the same game_id.

    Keeping the Steam app id here is what makes the re-import trick work: when
    we rebuild the database, we look up each Steam id, find the game_id we gave
    it last time, and reuse it. Published map versions keep working.
    """

    __tablename__ = "game_sources"

    source_name: Mapped[str] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.game_id"), nullable=False)
    source_url: Mapped[str | None]

    # When the snapshot was taken, as an ISO date string like "2025-03-01".
    retrieved_at: Mapped[str | None]

    game: Mapped["Game"] = relationship(back_populates="sources")

    __table_args__ = (Index("ix_game_sources_game_id", "game_id"),)


# ===========================================================================
# 3. features - the list of every trait a game can have
# ===========================================================================

# The nine groups our scrum doc approved. Anything outside this list is
# rejected by the database, which stops typos like "genres" or "Genre"
# from quietly creating a tenth category nobody notices.
VALID_CATEGORIES = (
    "genre",
    "gameplay",
    "mechanic",
    "structure",
    "theme",
    "multiplayer",
    "perspective",
    "platform",
    "tag",
)


class Feature(Base):
    """One row per trait, for example (genre, rpg) or (perspective, first_person).

    Why one table instead of separate genres / tags / platforms tables?
    Because the ML pipeline treats them all the same way: each one becomes a
    column in the feature matrix, and each category gets a weight. Keeping
    them in one table means adding a tenth category later is a config change,
    not a new table plus new code.

    `name` is the machine version (first_person) and `display_name` is what
    the user sees (First-Person). Keeping both means we can rename the label
    on screen without breaking anything that refers to the feature.
    """

    __tablename__ = "features"

    feature_id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(nullable=False)
    display_name: Mapped[str] = mapped_column(nullable=False)

    __table_args__ = (
        # (category, name) together must be unique. "rpg" can only exist once
        # inside "genre", but a different category could reuse the word.
        UniqueConstraint("category", "name", name="ux_features_category_name"),
        CheckConstraint(
            "category IN " + str(VALID_CATEGORIES), name="ck_features_category"
        ),
    )


# ===========================================================================
# 4. game_features - which games have which features
# ===========================================================================
class GameFeature(Base):
    """A plain link table. One row means "this game has this feature".

    A game with 4 genres and 20 tags has 24 rows here. There is no extra
    information on the row, just the pairing.
    """

    __tablename__ = "game_features"

    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.game_id"), primary_key=True
    )
    feature_id: Mapped[int] = mapped_column(
        ForeignKey("features.feature_id"), primary_key=True
    )

    __table_args__ = (
        # Required by our import rules. This one makes the backwards question
        # fast: "which games have feature 57?" Without it, filtering the map
        # by genre would scan every row.
        Index("ix_game_features_feature_id", "feature_id"),
    )


# ===========================================================================
# 4b. game_feature_coverage - ADDITION (team review)
# ===========================================================================
class GameFeatureCoverage(Base):
    """Tells apart "this game really has no stealth" from "nobody told us".

    Our import rules say to distinguish missing source information from a
    confirmed absence, and game_features cannot do that. It can only record
    that something IS there. The absence of a row is ambiguous.

    So we store one row per game per category with a verdict:

        present  we imported at least one feature in this category
        absent   the source gave us this field, and nothing in it matched
                 our current vocabulary
        unknown  the source gave us nothing to judge this category on

    Worth knowing: "absent" is relative to whatever vocabulary is in
    map_config.yaml right now. Add more aliases and re-run the import, and
    some of those absents turn into presents. That is expected.
    """

    __tablename__ = "game_feature_coverage"

    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.game_id"), primary_key=True
    )
    category: Mapped[str] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('present', 'absent', 'unknown')",
            name="ck_coverage_status",
        ),
        CheckConstraint(
            "category IN " + str(VALID_CATEGORIES), name="ck_coverage_category"
        ),
    )


# ===========================================================================
# 5. map_versions - one row per map the ML pipeline builds
# ===========================================================================
class MapVersion(Base):
    """Every time Kayne's pipeline produces a map, it gets a row here.

    Old versions are kept rather than overwritten. Exactly one of them is
    "live" at a time, marked by is_active = 1. Publishing a new map is really
    just switching which row has that flag, which means it happens instantly
    and can be undone by switching it back.

    The four snapshot columns exist so a map is reproducible later. If someone
    asks "why is Hades over there?", we can look up exactly which data file and
    which settings produced that map, instead of guessing.
    """

    __tablename__ = "map_versions"

    map_version_id: Mapped[str] = mapped_column(primary_key=True)
    created_at: Mapped[str | None]

    # building -> validated -> published, or failed if something went wrong.
    status: Mapped[str] = mapped_column(nullable=False, default="building")

    # SQLite has no real boolean type, so this is 0 or 1.
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    dataset_snapshot_ref: Mapped[str | None]   # where the input file was
    dataset_hash: Mapped[str | None]           # SHA-256, proves it is the same file
    config_snapshot_json: Mapped[str | None]   # the whole config at build time
    feature_artifact_ref: Mapped[str | None]   # where the feature matrices were saved

    __table_args__ = (
        CheckConstraint(
            "status IN ('building', 'validated', 'published', 'failed')",
            name="ck_map_versions_status",
        ),
        CheckConstraint(
            "is_active IN (0, 1)", name="ck_map_versions_is_active_bool"
        ),
        # Our doc says the active version must be a published one. This stops
        # a half-finished map from accidentally going live.
        CheckConstraint(
            "is_active = 0 OR status = 'published'",
            name="ck_active_must_be_published",
        ),
        # A "partial" unique index: it only applies to rows where is_active = 1.
        # The effect is that at most one row can be active at a time, enforced
        # by SQLite rather than by us remembering to check.
        Index(
            "ux_map_versions_single_active",
            "is_active",
            unique=True,
            sqlite_where=text("is_active = 1"),
        ),
    )


# ===========================================================================
# 6. clusters - the groups of similar games, per map version
# ===========================================================================
class Cluster(Base):
    """A cluster belongs to one map version, not to the database as a whole.

    Cluster 3 in map v1 and cluster 3 in map v2 are completely different
    groups of games. That is why map_version_id is part of the primary key.
    """

    __tablename__ = "clusters"

    map_version_id: Mapped[str] = mapped_column(
        ForeignKey("map_versions.map_version_id"), primary_key=True
    )
    cluster_id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str | None]
    color: Mapped[str | None]
    description: Mapped[str | None]


# ===========================================================================
# 7. map_games - where each game sits on the map
# ===========================================================================
class MapGame(Base):
    """The x/y coordinates and cluster for one game, in one map version.

    These are calculated once by the ML pipeline and then stored. The website
    never recalculates them. That is what makes REL 1 (everyone sees the same
    map) and REL 2 (two runs match to six decimals) possible at all.
    """

    __tablename__ = "map_games"

    map_version_id: Mapped[str] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.game_id"), primary_key=True
    )
    x: Mapped[float] = mapped_column(nullable=False)
    y: Mapped[float] = mapped_column(nullable=False)
    cluster_id: Mapped[int] = mapped_column(nullable=False)

    __table_args__ = (
        # A two-column foreign key. A single-column one pointing at
        # clusters.cluster_id would let a v2 game point at a v1 cluster, which
        # is nonsense. Checking both columns together is what actually enforces
        # "exactly one cluster FROM THE SAME map version".
        ForeignKeyConstraint(
            ["map_version_id", "cluster_id"],
            ["clusters.map_version_id", "clusters.cluster_id"],
            name="fk_map_games_cluster",
        ),
        Index("ix_map_games_version", "map_version_id"),
    )


# ===========================================================================
# 8. map_neighbors - the "similar games" lists
# ===========================================================================
class MapNeighbor(Base):
    """One row means "for game A, game B is the Nth most similar game".

    The info panel shows these when you click a game. Like positions, they are
    worked out once by the pipeline and stored, never computed live.
    """

    __tablename__ = "map_neighbors"

    map_version_id: Mapped[str] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(primary_key=True)
    neighbor_game_id: Mapped[int] = mapped_column(primary_key=True)
    similarity_score: Mapped[float | None]
    rank: Mapped[int] = mapped_column(nullable=False)  # 1 = most similar

    __table_args__ = (
        # Both ends of the pair have to be games that are actually ON this
        # map. Pointing at games.game_id would not be enough, because a game
        # can exist in the database without being included in a given map.
        ForeignKeyConstraint(
            ["map_version_id", "game_id"],
            ["map_games.map_version_id", "map_games.game_id"],
            name="fk_neighbors_source_in_map",
        ),
        ForeignKeyConstraint(
            ["map_version_id", "neighbor_game_id"],
            ["map_games.map_version_id", "map_games.game_id"],
            name="fk_neighbors_target_in_map",
        ),
        CheckConstraint(
            "game_id != neighbor_game_id", name="ck_neighbor_not_self"
        ),
        CheckConstraint("rank >= 1", name="ck_neighbor_rank_positive"),
        # ADDITION (team review)
        # Our doc says rank is unique within each game's list, but the primary
        # key it specifies does not actually enforce that: you could give two
        # different neighbours rank 3 and the database would accept it. This
        # index closes that gap.
        UniqueConstraint(
            "map_version_id",
            "game_id",
            "rank",
            name="ux_neighbors_rank_unique_per_game",
        ),
    )
