"""M0·B8 — скоупинг роутов workouts: чтение видит только записи владельца.

Залогинен user(id=1). Данные user(id=2) заведены напрямую в БД. Проверяем, что
GET-роуты /workouts не отдают чужие записи: список пуст/без чужого, одиночные → 404,
агрегаты (PR, прогресс по элементам) не считают чужое. 404 (а не 403) — чтобы не
раскрывать факт существования чужой записи.
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
from app.models.sport import Exercise, Sport
from app.models.user import User
from app.models.workout import (
    CardioLog,
    PersonalRecord,
    SkillLog,
    StrengthSet,
    WorkoutMedia,
    WorkoutSession,
)

EMAIL = "owner@example.com"
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
        session.add(User(email=EMAIL, password_hash=hash_password(PASSWORD)))  # id=1
        session.commit()

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    test_client = TestClient(app)
    test_client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def other(engine, tmp_path):
    """Чужой user(id=2) с полным набором записей: сессия, подход, кардио, скилл, медиа, PR.

    Файл медиа реально пишется на диск (абсолютный путь), чтобы 404 на /media был
    следствием именно проверки владельца, а не отсутствия файла."""
    media_file = tmp_path / "x.jpg"
    media_file.write_bytes(b"not-really-a-jpeg")
    with Session(engine) as session:
        session.add(User(email="other@example.com", password_hash=hash_password("x")))  # id=2
        sport = Sport(name="Чужой спорт", category="strength")
        session.add(sport)
        session.commit()
        session.refresh(sport)
        ex = Exercise(sport_id=sport.id, name="Чужое упражнение")
        session.add(ex)
        session.commit()
        session.refresh(ex)

        ws = WorkoutSession(user_id=2, date=dt.date(2026, 6, 21), title="Чужая тренировка")
        session.add(ws)
        session.commit()
        session.refresh(ws)

        session.add(StrengthSet(session_id=ws.id, exercise_id=ex.id, weight_kg=100, reps=5))
        cardio = CardioLog(session_id=ws.id, exercise_id=ex.id, distance_km=5, duration_sec=1500)
        skill = SkillLog(session_id=ws.id, exercise_id=ex.id, attempts=10, landed=5)
        media = WorkoutMedia(session_id=ws.id, media_path=str(media_file), media_type="image")
        pr = PersonalRecord(
            user_id=2, exercise_id=ex.id, metric="max_weight", date=dt.date(2026, 6, 21), value=100
        )
        for row in (cardio, skill, media, pr):
            session.add(row)
        session.commit()
        return {
            "ws": ws.id,
            "cardio": cardio.id,
            "skill": skill.id,
            "media": media.id,
            "exercise": ex.id,
        }


def test_list_workouts_excludes_other_user(client, other):
    assert client.get("/workouts").json() == []


def test_get_other_workout_returns_404(client, other):
    assert client.get(f"/workouts/{other['ws']}").status_code == 404


def test_metrics_of_other_workout_returns_404(client, other):
    assert client.get(f"/workouts/{other['ws']}/metrics").status_code == 404


def test_personal_records_exclude_other_user(client, other):
    assert client.get("/workouts/prs").json() == []


def test_get_other_cardio_returns_404(client, other):
    assert client.get(f"/workouts/cardio/{other['cardio']}").status_code == 404


def test_get_other_skill_returns_404(client, other):
    assert client.get(f"/workouts/skill/{other['skill']}").status_code == 404


def test_skill_progress_excludes_other_user(client, other):
    assert client.get("/workouts/skill/progress").json() == []


def test_get_other_media_returns_404(client, other):
    assert client.get(f"/workouts/media/{other['media']}").status_code == 404


def test_owner_sees_own_not_other(client, other):
    # своя тренировка создаётся через API (user_id=1) и видна; чужая (user_id=2) — нет
    sport = client.post("/sports", json={"name": "Мой спорт", "category": "strength"}).json()["id"]
    ex = client.post("/exercises", json={"sport_id": sport, "name": "Мой жим"}).json()["id"]
    own = client.post(
        "/workouts", json={"date": "2026-06-22", "sets": [{"exercise_id": ex, "reps": 5}]}
    ).json()
    body = client.get("/workouts").json()
    assert [w["id"] for w in body] == [own["id"]]  # ровно своя, без чужой
    assert client.get(f"/workouts/{own['id']}").status_code == 200  # свою читать можно
