"""Логирование силовой тренировки (S3.4): POST /workouts + readback.

Закрывает критерии карточки: силовая сессия с несколькими подходами сохраняется,
RPE и отдых (rest_sec) пишутся и возвращаются. Подход ссылается на упражнение
(FK exercise_id) — несуществующее упражнение даёт 404. Все роуты под сессией.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.user import User

EMAIL = "workouts@example.com"
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


def _make_exercise(client, name="Жим лёжа") -> int:
    sport_id = client.post("/sports", json={"name": name + " спорт", "type": "strength"}).json()[
        "id"
    ]
    return client.post("/exercises", json={"sport_id": sport_id, "name": name}).json()["id"]


def test_create_session_with_multiple_sets(client):
    ex = _make_exercise(client)
    resp = client.post(
        "/workouts",
        json={
            "date": "2026-06-21",
            "title": "Грудь+трицепс",
            "sets": [
                {"exercise_id": ex, "set_index": 1, "weight_kg": 60, "reps": 10},
                {"exercise_id": ex, "set_index": 2, "weight_kg": 65, "reps": 8},
                {"exercise_id": ex, "set_index": 3, "weight_kg": 70, "reps": 6},
            ],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] is not None
    assert body["date"] == "2026-06-21"
    assert body["title"] == "Грудь+трицепс"
    assert len(body["sets"]) == 3  # все три подхода сохранены
    assert [s["set_index"] for s in body["sets"]] == [1, 2, 3]
    assert [s["weight_kg"] for s in body["sets"]] == [60, 65, 70]


def test_rpe_and_rest_are_persisted(client):
    ex = _make_exercise(client)
    created = client.post(
        "/workouts",
        json={
            "date": "2026-06-21",
            "sets": [{"exercise_id": ex, "weight_kg": 80, "reps": 5, "rest_sec": 180, "rpe": 8.5}],
        },
    ).json()
    # читаем сессию заново — значения должны сохраниться в БД, а не только вернуться из POST
    resp = client.get(f"/workouts/{created['id']}")
    assert resp.status_code == 200
    s = resp.json()["sets"][0]
    assert s["rpe"] == 8.5
    assert s["rest_sec"] == 180


def test_session_requires_at_least_one_set(client):
    resp = client.post("/workouts", json={"date": "2026-06-21", "sets": []})
    assert resp.status_code == 422  # силовая сессия без подходов бессмысленна


def test_set_with_unknown_exercise_returns_404(client):
    resp = client.post(
        "/workouts",
        json={"date": "2026-06-21", "sets": [{"exercise_id": 999, "reps": 5}]},
    )
    assert resp.status_code == 404  # подход нельзя привязать к несуществующему упражнению


def test_unknown_sport_returns_404(client):
    ex = _make_exercise(client)
    resp = client.post(
        "/workouts",
        json={"date": "2026-06-21", "sport_id": 999, "sets": [{"exercise_id": ex, "reps": 5}]},
    )
    assert resp.status_code == 404  # вид спорта указан, но его нет


def test_read_unknown_session_returns_404(client):
    assert client.get("/workouts/999").status_code == 404


def test_list_sessions_newest_first(client):
    ex = _make_exercise(client)
    client.post(
        "/workouts",
        json={"date": "2026-06-19", "sets": [{"exercise_id": ex, "reps": 5}]},
    )
    client.post(
        "/workouts",
        json={"date": "2026-06-21", "sets": [{"exercise_id": ex, "reps": 5}]},
    )
    resp = client.get("/workouts")
    assert resp.status_code == 200
    dates = [w["date"] for w in resp.json()]
    assert dates == ["2026-06-21", "2026-06-19"]  # свежие сверху


def test_workouts_require_auth():
    app.dependency_overrides.clear()
    assert TestClient(app).get("/workouts").status_code == 401


# --- Кардио (S3.5) ---


def test_cardio_session_is_saved_and_readable(client):
    # критерий: кардио-сессия сохраняется. Пишем, потом читаем заново из БД.
    created = client.post(
        "/workouts/cardio",
        json={
            "date": "2026-06-21",
            "title": "Утренняя пробежка",
            "distance_km": 5,
            "duration_sec": 1500,
            "avg_hr": 150,
            "max_hr": 172,
        },
    )
    assert created.status_code == 201
    cardio_id = created.json()["id"]

    resp = client.get(f"/workouts/cardio/{cardio_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["date"] == "2026-06-21"
    assert body["title"] == "Утренняя пробежка"
    assert body["distance_km"] == 5
    assert body["duration_sec"] == 1500
    assert body["avg_hr"] == 150
    assert body["max_hr"] == 172  # пиковый пульс сохранён


def test_pace_is_computed_from_distance_and_time(client):
    # критерий: темп считается из дистанции/времени. 1500 сек / 5 км = 300 сек/км = 5:00 /км.
    body = client.post(
        "/workouts/cardio",
        json={"date": "2026-06-21", "distance_km": 5, "duration_sec": 1500},
    ).json()
    assert body["avg_pace"] == "5:00 /км"

    # дробный темп: 1650 / 5 = 330 сек/км = 5:30 /км
    other = client.post(
        "/workouts/cardio",
        json={"date": "2026-06-21", "distance_km": 5, "duration_sec": 1650},
    ).json()
    assert other["avg_pace"] == "5:30 /км"


def test_cardio_requires_positive_distance_and_duration(client):
    # без дистанции/времени темп не посчитать — это не валидная кардио-сессия
    assert (
        client.post(
            "/workouts/cardio",
            json={"date": "2026-06-21", "distance_km": 0, "duration_sec": 1500},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/workouts/cardio",
            json={"date": "2026-06-21", "distance_km": 5, "duration_sec": 0},
        ).status_code
        == 422
    )


def test_cardio_with_unknown_exercise_returns_404(client):
    resp = client.post(
        "/workouts/cardio",
        json={"date": "2026-06-21", "exercise_id": 999, "distance_km": 5, "duration_sec": 1500},
    )
    assert resp.status_code == 404  # нельзя привязать к несуществующему упражнению


def test_cardio_with_unknown_sport_returns_404(client):
    resp = client.post(
        "/workouts/cardio",
        json={"date": "2026-06-21", "sport_id": 999, "distance_km": 5, "duration_sec": 1500},
    )
    assert resp.status_code == 404


def test_read_unknown_cardio_returns_404(client):
    assert client.get("/workouts/cardio/999").status_code == 404
