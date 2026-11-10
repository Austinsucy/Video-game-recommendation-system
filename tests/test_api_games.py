import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import OperationalError

from backend.app.db import read_only_sessionmaker
from backend.app.main import app, get_session
from backend.app.models import Base, Feature, Game, GameFeature
from pipeline.publish import publish_map
from tests.conftest import make_clusters, make_neighbors, make_positions

ON_MAP = range(1, 13)


@pytest.fixture
def client(factory):
    def override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def populated(factory):
    with factory() as session, session.begin():
        game = session.get(Game, 1)
        game.cover_image_url = "https://img/1.jpg"
        game.release_year = 2020
        game.description = "Short blurb"
        game.rating = 98.0
        game.rating_scale = "0-100"
        game.playtime_hours = 12.5
        game.store_url = "https://store/1"
        session.add_all([
            Feature(feature_id=1, category="genre", name="rpg", display_name="RPG"),
            Feature(feature_id=2, category="platform", name="windows", display_name="Windows"),
            Feature(feature_id=3, category="platform", name="macos", display_name="macOS"),
            Feature(feature_id=4, category="theme", name="space", display_name="Space"),
            Feature(feature_id=5, category="tag", name="indie", display_name="Indie"),
        ])
        session.flush()
        session.add_all([GameFeature(game_id=1, feature_id=f) for f in range(1, 6)])


@pytest.fixture
def published(factory, populated):
    for version, ids in (("v1", list(ON_MAP)), ("v2", list(reversed(ON_MAP)))):
        publish_map(
            version, make_clusters(), make_positions(ON_MAP), make_neighbors(ids),
            session_factory=factory,
        )


def test_game_details(client, published):
    response = client.get("/games/1")

    assert response.status_code == 200
    assert response.json() == {
        "id": 1,
        "title": "Game 1",
        "coverUrl": "https://img/1.jpg",
        "releaseYear": 2020,
        "description": "Short blurb",
        "tags": ["Indie", "Space"],
        "platforms": ["Windows", "macOS"],
        "rating": 98.0,
        "ratingMax": 100,
        "averagePlaytimeHours": 12.5,
        "storeUrl": "https://store/1",
        "similarGames": [
            {"id": i, "title": f"Game {i}"} for i in range(12, 2, -1)
        ],
    }


def test_game_off_the_map_has_no_similar_games(client, published):
    response = client.get("/games/15")

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Game 15"
    assert body["similarGames"] == []
    assert body["tags"] == [] and body["platforms"] == []
    assert body["coverUrl"] is None


def test_no_active_map_version_means_no_similar_games(client, populated):
    assert client.get("/games/1").json()["similarGames"] == []


def test_a_game_without_reviews_has_no_rating(client, populated, factory):
    with factory() as session, session.begin():
        session.get(Game, 1).rating = -1.0

    body = client.get("/games/1").json()

    assert body["rating"] is None
    assert body["ratingMax"] is None


@pytest.mark.parametrize("game_id", ["9999", "0", "-1", str(2**63), "abc"])
def test_unknown_or_invalid_game_id_is_rejected(client, populated, game_id):
    assert client.get(f"/games/{game_id}").status_code in (404, 422)


@pytest.mark.parametrize("method", ["post", "put", "delete", "patch"])
def test_game_endpoints_reject_writing_methods(client, populated, factory, method):
    def counts():
        with factory() as session:
            return (
                session.scalar(select(func.count()).select_from(Game)),
                session.scalar(select(func.count()).select_from(GameFeature)),
                session.get(Game, 1).title,
            )

    before = counts()
    response = client.request(method.upper(), "/games/1", json={"title": "Changed"})

    assert response.status_code == 405
    assert counts() == before


def test_the_api_database_sessions_cannot_write(tmp_path):
    folder = tmp_path / "odd #name"
    folder.mkdir()
    db_path = folder / "games.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO games (game_id, title, title_search) VALUES (1, 'A', 'a')"
        ))
    engine.dispose()

    with read_only_sessionmaker(db_path)() as session:
        assert session.get(Game, 1).title == "A"
        with pytest.raises(OperationalError, match="readonly"):
            session.execute(text("UPDATE games SET title = 'B'"))
