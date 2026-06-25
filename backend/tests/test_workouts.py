"""Логирование силовой тренировки (S3.4): POST /workouts + readback.

Закрывает критерии карточки: силовая сессия с несколькими подходами сохраняется,
RPE и отдых (rest_sec) пишутся и возвращаются. Подход ссылается на упражнение
(FK exercise_id) — несуществующее упражнение даёт 404. Все роуты под сессией.
"""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401 — регистрирует все таблицы в SQLModel.metadata
from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.activity import ActivityDay
from app.models.user import User

EMAIL = "workouts@example.com"
PASSWORD = "right-password"


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def client(engine):
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
    payload = {"name": name + " спорт", "category": "strength"}
    sport_id = client.post("/sports", json=payload).json()["id"]
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


# --- Скилловые/элементы (S3.6) ---


def test_skill_session_is_saved_and_readable(client):
    # критерий: скилл-сессия сохраняется. Пишем, потом читаем заново из БД.
    ex = _make_exercise(client, name="Бэксайд 180")
    created = client.post(
        "/workouts/skill",
        json={
            "date": "2026-06-21",
            "title": "Вейкборд",
            "entries": [
                {"exercise_id": ex, "attempts": 10, "landed": 3, "notes": "первые приземления"},
            ],
        },
    )
    assert created.status_code == 201
    skill_id = created.json()["id"]

    resp = client.get(f"/workouts/skill/{skill_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["date"] == "2026-06-21"
    assert body["title"] == "Вейкборд"
    entry = body["entries"][0]
    assert entry["attempts"] == 10
    assert entry["landed"] == 3
    assert entry["notes"] == "первые приземления"


def test_skill_session_with_multiple_elements(client):
    ex1 = _make_exercise(client, name="Олли")
    ex2 = _make_exercise(client, name="Банни-хоп")
    body = client.post(
        "/workouts/skill",
        json={
            "date": "2026-06-21",
            "entries": [
                {"exercise_id": ex1, "attempts": 8, "landed": 5},
                {"exercise_id": ex2, "attempts": 6, "landed": 2},
            ],
        },
    ).json()
    assert len(body["entries"]) == 2  # оба элемента сохранены в одной сессии


def test_skill_progress_aggregates_by_element(client):
    # критерий: видно прогресс по элементам (landed/попытки) — суммируем по сессиям.
    ex = _make_exercise(client, name="Кикфлип")
    client.post(
        "/workouts/skill",
        json={"date": "2026-06-19", "entries": [{"exercise_id": ex, "attempts": 10, "landed": 1}]},
    )
    client.post(
        "/workouts/skill",
        json={"date": "2026-06-21", "entries": [{"exercise_id": ex, "attempts": 10, "landed": 4}]},
    )
    resp = client.get("/workouts/skill/progress")
    assert resp.status_code == 200
    progress = {item["exercise_id"]: item for item in resp.json()}
    p = progress[ex]
    assert p["attempts"] == 20  # 10 + 10
    assert p["landed"] == 5  # 1 + 4
    assert p["landing_rate"] == 0.25  # 5 / 20
    assert p["sessions"] == 2  # элемент встречался в двух сессиях
    assert p["exercise_name"] == "Кикфлип"


def test_skill_requires_at_least_one_entry(client):
    resp = client.post("/workouts/skill", json={"date": "2026-06-21", "entries": []})
    assert resp.status_code == 422  # скилл-сессия без элементов бессмысленна


def test_skill_landed_cannot_exceed_attempts(client):
    ex = _make_exercise(client, name="360")
    resp = client.post(
        "/workouts/skill",
        json={"date": "2026-06-21", "entries": [{"exercise_id": ex, "attempts": 3, "landed": 5}]},
    )
    assert resp.status_code == 422  # нельзя приземлить больше, чем попыток


def test_skill_attempts_must_be_positive(client):
    ex = _make_exercise(client, name="Грэб")
    resp = client.post(
        "/workouts/skill",
        json={"date": "2026-06-21", "entries": [{"exercise_id": ex, "attempts": 0, "landed": 0}]},
    )
    assert resp.status_code == 422  # без попыток нечего логировать


def test_skill_with_unknown_exercise_returns_404(client):
    resp = client.post(
        "/workouts/skill",
        json={"date": "2026-06-21", "entries": [{"exercise_id": 999, "attempts": 5, "landed": 1}]},
    )
    assert resp.status_code == 404  # нельзя привязать к несуществующему элементу


def test_skill_with_unknown_sport_returns_404(client):
    ex = _make_exercise(client, name="Шувит")
    resp = client.post(
        "/workouts/skill",
        json={
            "date": "2026-06-21",
            "sport_id": 999,
            "entries": [{"exercise_id": ex, "attempts": 5, "landed": 1}],
        },
    )
    assert resp.status_code == 404


def test_read_unknown_skill_returns_404(client):
    assert client.get("/workouts/skill/999").status_code == 404


# --- Связь тренировка ↔ день активности (S3.9) ---


def _add_activity_day(engine, date: str) -> None:
    """Заводит activity_day на дату напрямую (UI-импорт идёт через vision, тут он не нужен)."""
    with Session(engine) as session:
        session.add(ActivityDay(user_id=1, date=dt.date.fromisoformat(date), total_kcal=500))
        session.commit()


def test_strength_links_to_activity_day_when_day_exists(client, engine):
    # критерий: сессия линкуется к activity_day по дате при создании
    _add_activity_day(engine, "2026-06-21")
    ex = _make_exercise(client)
    body = client.post(
        "/workouts",
        json={"date": "2026-06-21", "sets": [{"exercise_id": ex, "reps": 5}]},
    ).json()
    assert body["activity_date"] == "2026-06-21"
    # связь читается обратно из БД, а не только из POST-ответа
    assert client.get(f"/workouts/{body['id']}").json()["activity_date"] == "2026-06-21"


def test_strength_not_linked_when_no_activity_day(client):
    # за дату нет дня активности → activity_date остаётся пустым (день не размечен)
    ex = _make_exercise(client)
    body = client.post(
        "/workouts",
        json={"date": "2026-06-21", "sets": [{"exercise_id": ex, "reps": 5}]},
    ).json()
    assert body["activity_date"] is None


def test_cardio_links_to_activity_day_when_day_exists(client, engine):
    _add_activity_day(engine, "2026-06-21")
    body = client.post(
        "/workouts/cardio",
        json={"date": "2026-06-21", "distance_km": 5, "duration_sec": 1500},
    ).json()
    assert body["activity_date"] == "2026-06-21"


def test_cardio_not_linked_when_no_activity_day(client):
    body = client.post(
        "/workouts/cardio",
        json={"date": "2026-06-21", "distance_km": 5, "duration_sec": 1500},
    ).json()
    assert body["activity_date"] is None


def test_skill_links_to_activity_day_when_day_exists(client, engine):
    _add_activity_day(engine, "2026-06-21")
    ex = _make_exercise(client, name="Кикфлип")
    body = client.post(
        "/workouts/skill",
        json={"date": "2026-06-21", "entries": [{"exercise_id": ex, "attempts": 5, "landed": 2}]},
    ).json()
    assert body["activity_date"] == "2026-06-21"


def test_link_only_matches_same_date(client, engine):
    # день активности 20-го, тренировка 21-го → связи нет (линк строго по совпадению даты)
    _add_activity_day(engine, "2026-06-20")
    ex = _make_exercise(client)
    body = client.post(
        "/workouts",
        json={"date": "2026-06-21", "sets": [{"exercise_id": ex, "reps": 5}]},
    ).json()
    assert body["activity_date"] is None
