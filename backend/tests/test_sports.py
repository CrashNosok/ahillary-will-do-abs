"""CRUD видов спорта (S3.1): создать/список/обновить/удалить + валидация категории.

Закрывает критерии карточки: полный CRUD над sport(name, category, description) и
проверка, что category ∈ таксономии SportCategory (M1·B14, иначе 422). Все роуты под сессией.
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
        json={"name": "Бег", "category": "endurance", "description": "Длительные кроссы"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] is not None
    assert body["name"] == "Бег"
    assert body["category"] == "endurance"
    assert body["description"] == "Длительные кроссы"


def test_create_sport_rejects_invalid_category(client):
    resp = client.post("/sports", json={"name": "Йога", "category": "flexibility"})
    assert resp.status_code == 422  # category вне таксономии SportCategory


def test_create_sport_rejects_retired_values(client):
    # cardio/skill сняты в M1·B14 (стали endurance/action) — теперь невалидны
    for retired in ("cardio", "skill"):
        resp = client.post("/sports", json={"name": f"Спорт-{retired}", "category": retired})
        assert resp.status_code == 422, retired


def test_create_sport_allows_each_valid_category(client):
    for cat in (
        "strength",
        "endurance",
        "combat",
        "team",
        "racket",
        "action",
        "precision",
        "artistic",
        "other",
    ):
        resp = client.post("/sports", json={"name": f"Спорт-{cat}", "category": cat})
        assert resp.status_code == 201, cat
        assert resp.json()["category"] == cat


def test_create_sport_requires_name_and_category(client):
    assert client.post("/sports", json={"category": "action"}).status_code == 422
    assert client.post("/sports", json={"name": "Без категории"}).status_code == 422


def test_list_sports_returns_all(client):
    client.post("/sports", json={"name": "Бег", "category": "endurance"})
    client.post("/sports", json={"name": "Жим", "category": "strength"})
    resp = client.get("/sports")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_read_sport_by_id(client):
    created = client.post("/sports", json={"name": "Планш", "category": "action"}).json()
    resp = client.get(f"/sports/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Планш"


def test_read_unknown_sport_returns_404(client):
    assert client.get("/sports/999").status_code == 404


def test_update_sport_changes_fields(client):
    created = client.post("/sports", json={"name": "Бег", "category": "endurance"}).json()
    resp = client.patch(
        f"/sports/{created['id']}",
        json={"description": "Темповые", "category": "action"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["description"] == "Темповые"
    assert body["category"] == "action"
    assert body["name"] == "Бег"  # не затёрто частичным апдейтом


def test_update_sport_rejects_invalid_category(client):
    created = client.post("/sports", json={"name": "Бег", "category": "endurance"}).json()
    resp = client.patch(f"/sports/{created['id']}", json={"category": "dancing"})
    assert resp.status_code == 422


def test_update_unknown_sport_returns_404(client):
    assert client.patch("/sports/999", json={"name": "x"}).status_code == 404


def test_delete_sport(client):
    created = client.post("/sports", json={"name": "Бег", "category": "endurance"}).json()
    resp = client.delete(f"/sports/{created['id']}")
    assert resp.status_code == 204
    assert client.get(f"/sports/{created['id']}").status_code == 404  # удалён


def test_delete_unknown_sport_returns_404(client):
    assert client.delete("/sports/999").status_code == 404


def test_duplicate_name_returns_409(client):
    client.post("/sports", json={"name": "Бег", "category": "endurance"})
    resp = client.post("/sports", json={"name": "Бег", "category": "strength"})
    assert resp.status_code == 409  # name уникален


def test_sports_require_auth():
    app.dependency_overrides.clear()
    assert TestClient(app).get("/sports").status_code == 401
