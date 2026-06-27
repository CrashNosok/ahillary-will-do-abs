"""M0·B10 — скоупинг агрегаторов и роутов цели/рекомендаций по владельцу.

Залогинен user(id=1). Данные user(id=2) заведены напрямую в БД. Проверяем, что
дашборд (services/dashboard.py), снапшот (services/snapshot.py), а также роуты
goals и recommendations видят и трогают только записи владельца:
- дашборд: флаги дня False, стрик 0, сводка дня нулевая на чужих данных;
- снапшот: все секции пусты/None при чужих данных;
- goals/recommendations: списки пусты, одиночные → 404 (не 403, чтобы не раскрывать
  существование чужой записи), создание активной цели не архивирует чужую активную.
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
from app.models.body import BodyMeasurement, InbodyMeasurement
from app.models.goal import GoalStatus, SmartGoal
from app.models.nutrition import FoodEntry
from app.models.recommendation import Recommendation
from app.models.user import User
from app.models.workout import WorkoutSession

EMAIL = "owner@example.com"
PASSWORD = "right-password"
TODAY = dt.date.today()


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
def other(engine):
    """Чужой user(id=2) с записями во всех источниках на сегодня + активная цель и рекомендация."""
    with Session(engine) as session:
        session.add(User(email="other@example.com", password_hash=hash_password("x")))  # id=2
        rows = [
            FoodEntry(user_id=2, date=TODAY, meal="Обед", product_name="x", kcal=600.0),
            ActivityDay(user_id=2, date=TODAY, total_kcal=2000, steps=9000),
            WorkoutSession(user_id=2, date=TODAY, title="чужая тренировка"),
            BodyMeasurement(user_id=2, date=TODAY, waist_cm=99.0),
            InbodyMeasurement(user_id=2, date=TODAY, weight_kg=99.0, body_fat_pct=33.0),
        ]
        goal = SmartGoal(
            user_id=2, status=GoalStatus.active, target_metrics_json={"weight_kg": 70.0}
        )
        rec = Recommendation(user_id=2, model="test-model", raw_text="чужая рекомендация")
        for row in (*rows, goal, rec):
            session.add(row)
        session.commit()
        session.refresh(goal)
        session.refresh(rec)
        return {"goal": goal.id, "rec": rec.id}


# --- дашборд ----------------------------------------------------------------


def test_dashboard_excludes_other_user(client, other):
    resp = client.get("/dashboard", params={"start": str(TODAY), "end": str(TODAY)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["current_streak"] == 0
    [day] = body["days"]
    assert not (
        day["has_food"] or day["has_activity"] or day["has_training"] or day["has_measurement"]
    )
    assert (body["today"]["kcal_in"], body["today"]["kcal_out"], body["today"]["deficit"]) == (
        0,
        0,
        0,
    )


# --- снапшот ----------------------------------------------------------------


def test_snapshot_excludes_other_user(client, other):
    snap = client.get("/snapshot").json()
    assert snap["goal"] is None  # чужая активная цель не попадает
    assert snap["nutrition"]["logged_days"] == 0
    assert snap["activity"]["logged_days"] == 0
    assert snap["measurements"] == {"latest_date": None, "values": {}}
    assert snap["inbody"] is None
    assert snap["training"]["sessions"] == 0
    assert snap["personal_records"] == []


# --- цели -------------------------------------------------------------------


def test_goals_list_excludes_other_user(client, other):
    assert client.get("/goals").json() == []


def test_goals_active_404_for_other_user(client, other):
    assert client.get("/goals/active").status_code == 404


def test_get_other_goal_returns_404(client, other):
    assert client.get(f"/goals/{other['goal']}").status_code == 404


def test_patch_other_goal_returns_404(client, other):
    assert client.patch(f"/goals/{other['goal']}", json={"why_notes": "x"}).status_code == 404


def test_archive_other_goal_returns_404(client, other):
    assert client.post(f"/goals/{other['goal']}/archive").status_code == 404


def test_create_active_goal_does_not_archive_other_user(client, engine, other):
    # У чужого юзера есть активная цель. Создание активной цели владельцем НЕ должно
    # её архивировать — инвариант «одна активная» скоупится по пользователю.
    resp = client.post("/goals", json={"target_metrics_json": {"weight_kg": 80}})
    assert resp.status_code == 201
    with Session(engine) as session:
        foreign = session.get(SmartGoal, other["goal"])
        assert foreign.status == GoalStatus.active  # чужая активная цель не тронута


# --- рекомендации -----------------------------------------------------------


def test_recommendations_list_excludes_other_user(client, other):
    assert client.get("/recommendations").json() == []


def test_get_other_recommendation_returns_404(client, other):
    assert client.get(f"/recommendations/{other['rec']}").status_code == 404


# --- владелец видит своё, но не чужое ---------------------------------------


def test_owner_sees_own_dashboard_and_goal(client, engine, other):
    # У владельца появились свои еда+активность на сегодня и своя цель.
    with Session(engine) as session:
        session.add(FoodEntry(user_id=1, date=TODAY, meal="Обед", product_name="y", kcal=400.0))
        session.add(ActivityDay(user_id=1, date=TODAY, total_kcal=1000))
        session.commit()
    own_goal = client.post("/goals", json={"target_metrics_json": {"weight_kg": 75}}).json()

    body = client.get("/dashboard", params={"start": str(TODAY), "end": str(TODAY)}).json()
    [day] = body["days"]
    assert day["has_food"] and day["has_activity"]  # видит своё
    assert not day["has_training"]  # чужую тренировку (user2) — нет
    assert body["today"]["kcal_in"] == 400  # сумма еды только владельца

    listed = client.get("/goals").json()
    assert [g["id"] for g in listed] == [own_goal["id"]]  # ровно своя цель, без чужой
    assert client.get("/goals/active").json()["id"] == own_goal["id"]
