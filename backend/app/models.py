"""SQLAlchemy models for the Goon Squad game map database.

Table layout follows "First Scrum Cycle: Game Database Structure" exactly.
Two additions are marked ADDITION - they exist because the scrum doc states a
rule that has no column to live in. Both are flagged for team review.
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
    pass


# --------------------------------------------------------------------------
# 1. games
# --------------------------------------------------------------------------
class Game(Base):
    __tablename__ = "games"

    game_id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(nullable=False)
    title_search: Mapped[str] = mapped_column(nullable=False)
    release_year: Mapped[int | None]
    description: Mapped[str | None]
    cover_image_url: Mapped[str | None]
    store_url: Mapped[str | None]
    playtime_hours: Mapped[float | None]
    rating: Mapped[float | None]
    rating_scale: Mapped[str | None]
    rating_count: Mapped[int | None]
    popularity: Mapped[float | None]

    # ADDITION (team review): the import rules say "preserve the original
    # dataset export and raw tags", but no column held them. This stores the
    # source tag->vote-count object verbatim as JSON text.
    raw_tags_json: Mapped[str | None]

    sources: Mapped[list["GameSource"]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )
    features: Mapped[list["Feature"]] = relationship(
        secondary="game_features", viewonly=True
    )

    # Required index on title_search.
    __table_args__ = (Index("ix_games_title_search", "title_search"),)


# --------------------------------------------------------------------------
# 2. game_sources
# --------------------------------------------------------------------------
class GameSource(Base):
    __tablename__ = "game_sources"

    source_name: Mapped[str] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.game_id"), nullable=False)
    source_url: Mapped[str | None]
    retrieved_at: Mapped[str | None]

    game: Mapped["Game"] = relationship(back_populates="sources")

    __table_args__ = (Index("ix_game_sources_game_id", "game_id"),)


# --------------------------------------------------------------------------
# 3. features
# --------------------------------------------------------------------------
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
    __tablename__ = "features"

    feature_id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(nullable=False)
    display_name: Mapped[str] = mapped_column(nullable=False)

    __table_args__ = (
        UniqueConstraint("category", "name", name="ux_features_category_name"),
        CheckConstraint(
            "category IN " + str(VALID_CATEGORIES), name="ck_features_category"
        ),
    )


# --------------------------------------------------------------------------
# 4. game_features
# --------------------------------------------------------------------------
class GameFeature(Base):
    __tablename__ = "game_features"

    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.game_id"), primary_key=True
    )
    feature_id: Mapped[int] = mapped_column(
        ForeignKey("features.feature_id"), primary_key=True
    )

    # Required index on feature_id.
    __table_args__ = (Index("ix_game_features_feature_id", "feature_id"),)


# --------------------------------------------------------------------------
# 4b. game_feature_coverage  -- ADDITION (team review)
# --------------------------------------------------------------------------
class GameFeatureCoverage(Base):
    """Separates "the source said nothing" from "the game genuinely lacks this".

    The import rules require distinguishing missing source information from a
    confirmed absence, which `game_features` alone cannot express: it can only
    record presence. One row per game per category.

    status:
      present  - at least one feature of this category was imported
      absent   - the source supplied this category and the game had none
      unknown  - the source supplied nothing we could judge this category on
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


# --------------------------------------------------------------------------
# 5. map_versions
# --------------------------------------------------------------------------
class MapVersion(Base):
    __tablename__ = "map_versions"

    map_version_id: Mapped[str] = mapped_column(primary_key=True)
    created_at: Mapped[str | None]
    status: Mapped[str] = mapped_column(nullable=False, default="building")
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dataset_snapshot_ref: Mapped[str | None]
    dataset_hash: Mapped[str | None]
    config_snapshot_json: Mapped[str | None]
    feature_artifact_ref: Mapped[str | None]

    __table_args__ = (
        CheckConstraint(
            "status IN ('building', 'validated', 'published', 'failed')",
            name="ck_map_versions_status",
        ),
        # "Allow only one active version. It must have published status."
        CheckConstraint(
            "is_active IN (0, 1)", name="ck_map_versions_is_active_bool"
        ),
        CheckConstraint(
            "is_active = 0 OR status = 'published'",
            name="ck_active_must_be_published",
        ),
        # Partial unique index: at most one row may have is_active = 1.
        Index(
            "ux_map_versions_single_active",
            "is_active",
            unique=True,
            sqlite_where=text("is_active = 1"),
        ),
    )


# --------------------------------------------------------------------------
# 6. clusters
# --------------------------------------------------------------------------
class Cluster(Base):
    __tablename__ = "clusters"

    map_version_id: Mapped[str] = mapped_column(
        ForeignKey("map_versions.map_version_id"), primary_key=True
    )
    cluster_id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str | None]
    color: Mapped[str | None]
    description: Mapped[str | None]


# --------------------------------------------------------------------------
# 7. map_games
# --------------------------------------------------------------------------
class MapGame(Base):
    __tablename__ = "map_games"

    map_version_id: Mapped[str] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(
        ForeignKey("games.game_id"), primary_key=True
    )
    x: Mapped[float] = mapped_column(nullable=False)
    y: Mapped[float] = mapped_column(nullable=False)
    cluster_id: Mapped[int] = mapped_column(nullable=False)

    __table_args__ = (
        # "exactly one cluster from the same map version" - the composite FK is
        # what actually enforces "from the same map version".
        ForeignKeyConstraint(
            ["map_version_id", "cluster_id"],
            ["clusters.map_version_id", "clusters.cluster_id"],
            name="fk_map_games_cluster",
        ),
        Index("ix_map_games_version", "map_version_id"),
    )


# --------------------------------------------------------------------------
# 8. map_neighbors
# --------------------------------------------------------------------------
class MapNeighbor(Base):
    __tablename__ = "map_neighbors"

    map_version_id: Mapped[str] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(primary_key=True)
    neighbor_game_id: Mapped[int] = mapped_column(primary_key=True)
    similarity_score: Mapped[float | None]
    rank: Mapped[int] = mapped_column(nullable=False)

    __table_args__ = (
        # "Both games must exist in map_games for that version."
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
        # "A game cannot recommend itself."
        CheckConstraint(
            "game_id != neighbor_game_id", name="ck_neighbor_not_self"
        ),
        CheckConstraint("rank >= 1", name="ck_neighbor_rank_positive"),
        # ADDITION (team review): "rank ... is unique within each game's
        # versioned list" is not enforceable by the stated primary key alone.
        UniqueConstraint(
            "map_version_id",
            "game_id",
            "rank",
            name="ux_neighbors_rank_unique_per_game",
        ),
    )
