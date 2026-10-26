"""Write a generated map into the database and activate it safely.

Kayne and Austin's pipeline produces coordinates, clusters and neighbours.
This module is the only thing that writes them, and it enforces the rule that
a failed build must leave the previously published version active.

Shape of the inputs:
    clusters  = [{"cluster_id": 0, "display_name": ..., "color": ..., "description": ...}]
    positions = [{"game_id": 1, "x": 0.1, "y": 2.3, "cluster_id": 0}]
    neighbors = [{"game_id": 1, "neighbor_game_id": 7, "similarity_score": 0.9, "rank": 1}]
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone

from sqlalchemy import func, select, update

from backend.app.db import SessionLocal
from backend.app.models import Cluster, Game, MapGame, MapNeighbor, MapVersion

MAX_GAMES = 1100          # CON 3
MIN_NEIGHBORS = 10        # scrum doc: 10-15 neighbours per game
MAX_NEIGHBORS = 15


class MapValidationError(ValueError):
    """Raised when a map is incomplete. The caller's transaction rolls back."""


def validate(clusters, positions, neighbors, known_game_ids: set[int]) -> None:
    if not positions:
        raise MapValidationError("map contains no games")
    if len(positions) > MAX_GAMES:
        raise MapValidationError(
            f"{len(positions)} games exceeds the {MAX_GAMES} cap; "
            "retest PERF 1-3 before publishing a larger map"
        )

    cluster_ids = {c["cluster_id"] for c in clusters}
    if len(cluster_ids) != len(clusters):
        raise MapValidationError("duplicate cluster_id")

    game_ids = [p["game_id"] for p in positions]
    if len(game_ids) != len(set(game_ids)):
        raise MapValidationError("a game appears twice in the map")
    unknown = set(game_ids) - known_game_ids
    if unknown:
        raise MapValidationError(f"{len(unknown)} mapped games are not in `games`")

    for p in positions:
        for axis in ("x", "y"):
            v = p[axis]
            if v is None or not isinstance(v, (int, float)) or not math.isfinite(float(v)):
                raise MapValidationError(
                    f"game {p['game_id']} has a non-finite {axis} coordinate"
                )
        if p["cluster_id"] not in cluster_ids:
            raise MapValidationError(
                f"game {p['game_id']} points at cluster {p['cluster_id']}, "
                "which this version does not define"
            )

    mapped = set(game_ids)
    per_game: dict[int, list[int]] = {}
    for n in neighbors:
        if n["game_id"] == n["neighbor_game_id"]:
            raise MapValidationError(f"game {n['game_id']} recommends itself")
        if n["game_id"] not in mapped or n["neighbor_game_id"] not in mapped:
            raise MapValidationError(
                "a neighbour pair references a game outside this map version"
            )
        per_game.setdefault(n["game_id"], []).append(n["rank"])

    for game_id, ranks in per_game.items():
        if len(ranks) != len(set(ranks)):
            raise MapValidationError(f"game {game_id} has duplicate neighbour ranks")
        if sorted(ranks) != list(range(1, len(ranks) + 1)):
            raise MapValidationError(
                f"game {game_id} neighbour ranks must start at 1 and be contiguous"
            )
        if not MIN_NEIGHBORS <= len(ranks) <= MAX_NEIGHBORS:
            raise MapValidationError(
                f"game {game_id} has {len(ranks)} neighbours; "
                f"{MIN_NEIGHBORS}-{MAX_NEIGHBORS} required"
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
    """Validate, write and activate in ONE transaction.

    Any exception rolls the whole thing back, so the previously published
    version stays active and no partial version is ever saved.
    """
    with session_factory() as s, s.begin():
        if s.get(MapVersion, map_version_id) is not None:
            raise MapValidationError(f"map version {map_version_id!r} already exists")

        known = set(s.scalars(select(Game.game_id)).all())
        validate(clusters, positions, neighbors, known)

        s.add(
            MapVersion(
                map_version_id=map_version_id,
                created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                status="building",
                is_active=0,
                dataset_snapshot_ref=dataset_snapshot_ref,
                dataset_hash=dataset_hash,
                config_snapshot_json=json.dumps(config_snapshot, default=str)
                if config_snapshot
                else None,
                feature_artifact_ref=feature_artifact_ref,
            )
        )
        s.flush()

        s.execute(
            Cluster.__table__.insert(),
            [{"map_version_id": map_version_id, **c} for c in clusters],
        )
        s.execute(
            MapGame.__table__.insert(),
            [{"map_version_id": map_version_id, **p} for p in positions],
        )
        if neighbors:
            s.execute(
                MapNeighbor.__table__.insert(),
                [{"map_version_id": map_version_id, **n} for n in neighbors],
            )
        s.flush()

        # Cross-check what actually landed before trusting it.
        written = s.scalar(
            select(func.count())
            .select_from(MapGame)
            .where(MapGame.map_version_id == map_version_id)
        )
        if written != len(positions):
            raise MapValidationError(
                f"wrote {written} positions but expected {len(positions)}"
            )

        s.execute(
            update(MapVersion)
            .where(MapVersion.map_version_id == map_version_id)
            .values(status="validated")
        )

        # Deactivate the old version, then promote this one. Order matters:
        # the partial unique index allows only one active row at a time.
        s.execute(update(MapVersion).values(is_active=0))
        s.execute(
            update(MapVersion)
            .where(MapVersion.map_version_id == map_version_id)
            .values(status="published", is_active=1)
        )


def mark_failed(map_version_id: str, session_factory=SessionLocal) -> None:
    """Record a build that did not make it, without touching the active one."""
    with session_factory() as s, s.begin():
        v = s.get(MapVersion, map_version_id)
        if v is None:
            s.add(
                MapVersion(
                    map_version_id=map_version_id,
                    created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    status="failed",
                    is_active=0,
                )
            )
        else:
            v.status = "failed"
            v.is_active = 0
