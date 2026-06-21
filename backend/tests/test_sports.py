"""CRUD видов спорта (S3.1): создать/список/обновить/удалить + валидация типа.

Закрывает критерии карточки: полный CRUD над sport(name, type, description) и
проверка, что type ∈ {strength, cardio, skill} (иначе 422). Все роуты под сессией.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.user import User

EMAIL = "sports@example.com"
PASSWORD = "right-password"


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(email=EMAIL, password_hash=hash_password(PASSWORD)))
        session.commit()

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    test_client = TestClient(app)
    test_client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    yield test_client
    app.dependency_overrides.clear()


def test_create_sport_returns_201_with_fields(client):
    resp = client.post(
        "/sports",
        json={"name": "Бег", "type": "cardio", "description": "Длительные кроссы"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] is not None
    assert body["name"] == "Бег"
    assert body["type"] == "cardio"
    assert body["description"] == "Длительные кроссы"


def test_create_sport_rejects_invalid_type(client):
    resp = client.post("/sports", json={"name": "Йога", "type": "flexibility"})
    assert resp.status_code == 422  # type вне strength/cardio/skill


def test_create_sport_allows_each_valid_type(client):
    for kind in ("strength", "cardio", "skill"):
        resp = client.post("/sports", json={"name": f"Спорт-{kind}", "type": kind})
        assert resp.status_code == 201, kind
        assert resp.json()["type"] == kind


def test_create_sport_requires_name_and_type(client):
    assert client.post("/sports", json={"type": "skill"}).status_code == 422
    assert client.post("/sports", json={"name": "Без типа"}).status_code == 422


def test_list_sports_returns_all(client):
    client.post("/sports", json={"name": "Бег", "type": "cardio"})
    client.post("/sports", json={"name": "Жим", "type": "strength"})
    resp = client.get("/sports")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_read_sport_by_id(client):
    created = client.post("/sports", json={"name": "Планш", "type": "skill"}).json()
    resp = client.get(f"/sports/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Планш"


def test_read_unknown_sport_returns_404(client):
    assert client.get("/sports/999").status_code == 404


def test_update_sport_changes_fields(client):
    created = client.post("/sports", json={"name": "Бег", "type": "cardio"}).json()
    resp = client.patch(
        f"/sports/{created['id']}",
        json={"description": "Темповые", "type": "skill"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["description"] == "Темповые"
    assert body["type"] == "skill"
    assert body["name"] == "Бег"  # не затёрто частичным апдейтом


def test_update_sport_rejects_invalid_type(client):
    created = client.post("/sports", json={"name": "Бег", "type": "cardio"}).json()
    resp = client.patch(f"/sports/{created['id']}", json={"type": "dancing"})
    assert resp.status_code == 422


def test_update_unknown_sport_returns_404(client):
    assert client.patch("/sports/999", json={"name": "x"}).status_code == 404


def test_delete_sport(client):
    created = client.post("/sports", json={"name": "Бег", "type": "cardio"}).json()
    resp = client.delete(f"/sports/{created['id']}")
    assert resp.status_code == 204
    assert client.get(f"/sports/{created['id']}").status_code == 404  # удалён


def test_delete_unknown_sport_returns_404(client):
    assert client.delete("/sports/999").status_code == 404


def test_duplicate_name_returns_409(client):
    client.post("/sports", json={"name": "Бег", "type": "cardio"})
    resp = client.post("/sports", json={"name": "Бег", "type": "strength"})
    assert resp.status_code == 409  # name уникален


def test_sports_require_auth():
    app.dependency_overrides.clear()
    assert TestClient(app).get("/sports").status_code == 401
