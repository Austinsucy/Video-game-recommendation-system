"""
Saves a finished map into the database and makes it the live one.

WHO USES THIS
    Kayne and Austin's ML pipeline. It works out coordinates, clusters and
    similar-game lists, then calls publish_map() to store them. This module is
    the only thing allowed to write to the map tables.

WHAT IT GUARANTEES
    Our REL 4 requirement says a failed build must leave the previous map
    active. The way we achieve that is simple: validate everything first, then
    do all the writing inside a single transaction. If anything at all goes
    wrong, the database rolls back to exactly how it was. There is no state
    where half a map is published.

WHAT YOU PASS IN
    clusters   [{"cluster_id": 0, "display_name": "Co-op shooters",
                 "color": "#4C7BD9", "description": ""}]
    positions  [{"game_id": 1, "x": 0.12, "y": -3.4, "cluster_id": 0}]
    neighbors  [{"game_id": 1, "neighbor_game_id": 7,
                 "similarity_score": 0.91, "rank": 1}]
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone

from sqlalchemy import func, select, update

from backend.app.db import SessionLocal
from backend.app.models import Cluster, Game, MapGame, MapNeighbor, MapVersion

MAX_GAMES = 1100        # CON 3. Above this we would need to retest performance.
MIN_NEIGHBORS = 10      # our scrum doc asks for 10 to 15 per game
MAX_NEIGHBORS = 15


class MapValidationError(ValueError):
    """Raised when a map is not fit to publish.

    Because publish_map() raises this inside a transaction, raising it is also
    what rolls everything back. The error message is written to say exactly
    what is wrong so Kayne can fix it without reading this file.
    """


def validate(clusters, positions, neighbors, known_game_ids: set[int]) -> None:
    """Check a map thoroughly before any of it is written.

    Everything here is checked in Python rather than left to the database,
    because we want ALL the problems reported with a useful message, not just
    whichever constraint SQLite happens to hit first.
    """
    if not positions:
        raise MapValidationError("the map has no games in it")

    if len(positions) > MAX_GAMES:
        raise MapValidationError(
            f"{len(positions)} games is over the {MAX_GAMES} cap from CON 3. "
            "We would need to re-test the PERF requirements before going bigger."
        )

    # --- clusters ---
    cluster_ids = {c["cluster_id"] for c in clusters}
    if len(cluster_ids) != len(clusters):
        raise MapValidationError("two clusters share the same cluster_id")

    # --- positions ---
    game_ids = [p["game_id"] for p in positions]
    if len(game_ids) != len(set(game_ids)):
        raise MapValidationError("the same game appears twice in the map")

    unknown = set(game_ids) - known_game_ids
    if unknown:
        raise MapValidationError(
            f"{len(unknown)} games in the map are not in the `games` table. "
            f"First few: {sorted(unknown)[:5]}"
        )

    for p in positions:
        for axis in ("x", "y"):
            value = p[axis]
            # This check has to happen here, not as a database constraint.
            # SQLite quietly turns NaN into NULL and accepts infinity, so a
            # CHECK would not catch either. A NaN coordinate means the node
            # silently vanishes from the map, which is a horrible bug to chase.
            if (value is None
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))):
                raise MapValidationError(
                    f"game {p['game_id']} has a {axis} value of {value!r}, "
                    "which is not a finite number"
                )
        if p["cluster_id"] not in cluster_ids:
            raise MapValidationError(
                f"game {p['game_id']} is assigned to cluster {p['cluster_id']}, "
                "but this map version does not define that cluster"
            )

    # --- neighbours ---
    mapped = set(game_ids)
    ranks_by_game: dict[int, list[int]] = {}

    for n in neighbors:
        if n["game_id"] == n["neighbor_game_id"]:
            raise MapValidationError(
                f"game {n['game_id']} is listed as similar to itself"
            )
        if n["game_id"] not in mapped or n["neighbor_game_id"] not in mapped:
            raise MapValidationError(
                "a similar-games pair points at a game that is not on this map"
            )
        ranks_by_game.setdefault(n["game_id"], []).append(n["rank"])

    for game_id, ranks in ranks_by_game.items():
        if len(ranks) != len(set(ranks)):
            raise MapValidationError(
                f"game {game_id} has two neighbours with the same rank"
            )
        if sorted(ranks) != list(range(1, len(ranks) + 1)):
            raise MapValidationError(
                f"game {game_id} has ranks {sorted(ranks)}. They should start "
                "at 1 and count up with no gaps."
            )
        if not MIN_NEIGHBORS <= len(ranks) <= MAX_NEIGHBORS:
            raise MapValidationError(
                f"game {game_id} has {len(ranks)} neighbours. Our scrum doc "
                f"asks for {MIN_NEIGHBORS} to {MAX_NEIGHBORS}."
            )


def publish_map(
    map_version_id: str,
    clusters,
    positions,
    neighbors,
    *,
    dataset_snapshot_ref: str | None = None,
    dataset_hash: str | None = None,
    config_snapshot: dict | None = None,
    feature_artifact_ref: str | None = None,
    session_factory=SessionLocal,
) -> None:
    """Validate a map, write it, and switch it live. All or nothing.

    The session_factory argument is only there so tests can hand in an
    in-memory database. Normal callers leave it alone.
    """
    with session_factory() as session, session.begin():

        if session.get(MapVersion, map_version_id) is not None:
            raise MapValidationError(
                f"a map version called {map_version_id!r} already exists. "
                "Pick a new name rather than overwriting history."
            )

        known_game_ids = set(session.scalars(select(Game.game_id)).all())
        validate(clusters, positions, neighbors, known_game_ids)

        # Start as "building" and NOT active. If we crash from here on, the
        # rollback removes this row entirely and the old map stays live.
        session.add(MapVersion(
            map_version_id=map_version_id,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            status="building",
            is_active=0,
            dataset_snapshot_ref=dataset_snapshot_ref,
            dataset_hash=dataset_hash,
            config_snapshot_json=(
                json.dumps(config_snapshot, default=str) if config_snapshot else None
            ),
            feature_artifact_ref=feature_artifact_ref,
        ))
        session.flush()   # make the parent row exist before children point at it

        session.execute(
            Cluster.__table__.insert(),
            [{"map_version_id": map_version_id, **c} for c in clusters],
        )
        session.execute(
            MapGame.__table__.insert(),
            [{"map_version_id": map_version_id, **p} for p in positions],
        )
        if neighbors:
            session.execute(
                MapNeighbor.__table__.insert(),
                [{"map_version_id": map_version_id, **n} for n in neighbors],
            )
        session.flush()

        # Belt and braces: count what actually landed. If a database rule
        # silently dropped rows, we would rather fail than publish a map with
        # games missing from it.
        written = session.scalar(
            select(func.count())
            .select_from(MapGame)
            .where(MapGame.map_version_id == map_version_id)
        )
        if written != len(positions):
            raise MapValidationError(
                f"expected to write {len(positions)} positions but only "
                f"{written} are in the database"
            )

        session.execute(
            update(MapVersion)
            .where(MapVersion.map_version_id == map_version_id)
            .values(status="validated")
        )

        # Switch over. Order matters: turn the old one off first, because the
        # database only allows one active row at a time and would reject
        # having two active for even a moment.
        session.execute(update(MapVersion).values(is_active=0))
        session.execute(
            update(MapVersion)
            .where(MapVersion.map_version_id == map_version_id)
            .values(status="published", is_active=1)
        )


def mark_failed(map_version_id: str, session_factory=SessionLocal) -> None:
    """Record that a build did not work out, without disturbing the live map.

    Useful for keeping a history of attempts. The currently published version
    is untouched.
    """
    with session_factory() as session, session.begin():
        version = session.get(MapVersion, map_version_id)
        if version is None:
            session.add(MapVersion(
                map_version_id=map_version_id,
                created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                status="failed",
                is_active=0,
            ))
        else:
            version.status = "failed"
            version.is_active = 0
