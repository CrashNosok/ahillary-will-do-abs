"""CRUD упражнений библиотеки (S3.2): создать/список/обновить/удалить.

Закрывает критерии карточки: добавить упражнение к виду спорта и получить список
упражнений по виду спорта (фильтр ?sport_id). Поля упражнения: sport_id, name, unit, notes.
sport_id обязателен и должен ссылаться на существующий вид спорта (иначе 404).
Все роуты под сессией.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.user import User

EMAIL = "exercises@example.com"
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


def _make_sport(client, name="Калистеника", category="action") -> int:
    return client.post("/sports", json={"name": name, "category": category}).json()["id"]


def test_create_exercise_returns_201_with_fields(client):
    sport_id = _make_sport(client)
    resp = client.post(
        "/exercises",
        json={
            "sport_id": sport_id,
            "name": "Подтягивания",
            "unit": "повторы",
            "notes": "хват сверху",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] is not None
    assert body["sport_id"] == sport_id
    assert body["name"] == "Подтягивания"
    assert body["unit"] == "повторы"
    assert body["notes"] == "хват сверху"


def test_create_exercise_requires_sport_and_name(client):
    sport_id = _make_sport(client)
    assert client.post("/exercises", json={"name": "Без спорта"}).status_code == 422
    assert client.post("/exercises", json={"sport_id": sport_id}).status_code == 422


def test_create_exercise_unknown_sport_returns_404(client):
    resp = client.post("/exercises", json={"sport_id": 999, "name": "Сирота"})
    assert resp.status_code == 404  # вида спорта нет — упражнение не привязать


def test_list_exercises_by_sport(client):
    sport_a = _make_sport(client, name="Бег", category="endurance")
    sport_b = _make_sport(client, name="Силовая", category="strength")
    client.post("/exercises", json={"sport_id": sport_a, "name": "Интервалы"})
    client.post("/exercises", json={"sport_id": sport_a, "name": "Кросс"})
    client.post("/exercises", json={"sport_id": sport_b, "name": "Жим лёжа"})

    resp = client.get("/exercises", params={"sport_id": sport_a})
    assert resp.status_code == 200
    names = [e["name"] for e in resp.json()]
    assert sorted(names) == ["Интервалы", "Кросс"]  # только упражнения вида спорта A


def test_list_all_exercises(client):
    sport_id = _make_sport(client)
    client.post("/exercises", json={"sport_id": sport_id, "name": "Отжимания"})
    client.post("/exercises", json={"sport_id": sport_id, "name": "Приседания"})
    resp = client.get("/exercises")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_read_exercise_by_id(client):
    sport_id = _make_sport(client)
    created = client.post("/exercises", json={"sport_id": sport_id, "name": "Планка"}).json()
    resp = client.get(f"/exercises/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Планка"


def test_read_unknown_exercise_returns_404(client):
    assert client.get("/exercises/999").status_code == 404


def test_update_exercise_changes_fields(client):
    sport_id = _make_sport(client)
    created = client.post(
        "/exercises", json={"sport_id": sport_id, "name": "Выпады", "unit": "повторы"}
    ).json()
    resp = client.patch(
        f"/exercises/{created['id']}",
        json={"unit": "сек", "notes": "на каждую ногу"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["unit"] == "сек"
    assert body["notes"] == "на каждую ногу"
    assert body["name"] == "Выпады"  # не затёрто частичным апдейтом


def test_update_unknown_exercise_returns_404(client):
    assert client.patch("/exercises/999", json={"name": "x"}).status_code == 404


def test_delete_exercise(client):
    sport_id = _make_sport(client)
    created = client.post("/exercises", json={"sport_id": sport_id, "name": "Берпи"}).json()
    resp = client.delete(f"/exercises/{created['id']}")
    assert resp.status_code == 204
    assert client.get(f"/exercises/{created['id']}").status_code == 404  # удалён


def test_delete_unknown_exercise_returns_404(client):
    assert client.delete("/exercises/999").status_code == 404


def test_exercises_require_auth():
    app.dependency_overrides.clear()
    assert TestClient(app).get("/exercises").status_code == 401
