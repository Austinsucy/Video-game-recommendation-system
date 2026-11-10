"""
The read-only game API (GIP 1).

The API never writes.
"""
import os
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db import ReadOnlySessionLocal
from backend.app.models import Feature, Game, GameFeature, MapNeighbor, MapVersion


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SimilarGame(ApiModel):
    id: int
    title: str


class GameDetails(ApiModel):
    id: int
    title: str
    cover_url: str | None
    release_year: int | None
    description: str | None
    tags: list[str]
    platforms: list[str]
    rating: float | None
    rating_max: int | None
    average_playtime_hours: float | None
    store_url: str | None
    similar_games: list[SimilarGame]


def get_session() -> Iterator[Session]:
    with ReadOnlySessionLocal() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]

# SQLite integers stop at 2**63 - 1; a larger id would fail inside the driver.
GameId = Annotated[int, Path(ge=1, le=2**63 - 1)]


CATEGORIES_THE_WEBSITE_READS_FROM_MAP_DB = ("genre",)


def scale_max(rating_scale: str) -> int:
    """'0-100' -> 100"""
    return int(rating_scale.rpartition("-")[2])


app = FastAPI(title="Video game map API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.environ.get(
            "CORS_ALLOW_ORIGINS", "http://localhost:5173,http://localhost:4173"
        ).split(",")
        if origin.strip()
    ],
    allow_methods=["GET"],
)


@app.get("/games/{game_id}")
def get_game(game_id: GameId, session: SessionDep) -> GameDetails:
    game = session.get(Game, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    features = session.execute(
        select(Feature.category, Feature.display_name)
        .join(GameFeature, GameFeature.feature_id == Feature.feature_id)
        .where(
            GameFeature.game_id == game_id,
            Feature.category.not_in(CATEGORIES_THE_WEBSITE_READS_FROM_MAP_DB),
        )
        .order_by(Feature.category, Feature.display_name)
    ).all()

    neighbours = session.execute(
        select(MapNeighbor.neighbor_game_id, Game.title)
        .join(MapVersion, MapVersion.map_version_id == MapNeighbor.map_version_id)
        .join(Game, Game.game_id == MapNeighbor.neighbor_game_id)
        .where(MapVersion.is_active == 1, MapNeighbor.game_id == game_id)
        .order_by(MapNeighbor.rank)
    ).all()

    has_reviews = game.rating is not None and game.rating >= 0

    return GameDetails(
        id=game.game_id,
        title=game.title,
        cover_url=game.cover_image_url,
        release_year=game.release_year,
        description=game.description,
        tags=[name for category, name in features if category != "platform"],
        platforms=[name for category, name in features if category == "platform"],
        rating=game.rating if has_reviews else None,
        rating_max=(
            scale_max(game.rating_scale)
            if has_reviews and game.rating_scale else None
        ),
        average_playtime_hours=game.playtime_hours,
        store_url=game.store_url,
        similar_games=[SimilarGame(id=gid, title=title) for gid, title in neighbours],
    )
