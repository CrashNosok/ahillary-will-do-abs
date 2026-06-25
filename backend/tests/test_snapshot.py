"""Агрегатор входа для LLM (S4.1): один снапшот со всеми сигналами + устойчивость к пропускам.

Закрывает критерии карточки:
- «один объект со всеми сигналами» — снапшот содержит все секции (цель, питание,
  активность/дефицит, замеры, InBody, тренировки, PR) с осмысленными значениями;
- «устойчив к пропускам данных» — на пустой БД и при частичных данных снапшот
  собирается целиком без исключений, пустые секции отдают null / пусто / 0.

Снапшот проверяем и сервисом напрямую (детерминированно по дате), и через
HTTP-роут /snapshot (под сессией).
"""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.activity import ActivityDay
from app.models.body import BodyMeasurement, InbodyMeasurement
from app.models.deficit import DeficitDay
from app.models.goal import SmartGoal
from app.models.nutrition import FoodEntry
from app.models.sport import Exercise, Sport, SportType
from app.models.user import User
from app.models.workout import CardioLog, PersonalRecord, StrengthSet, WorkoutSession
from app.services import snapshot as snapshot_service

EMAIL = "snapshot@example.com"
PASSWORD = "right-password"
# Окно снапшота отсчитывается от сегодня; роут /snapshot end не принимает, поэтому
# сиды привязываем к реальному today() — тесты не зависят от конкретной даты прогона.
TODAY = dt.date.today()


@pytest.fixture
def ctx():
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
    client = TestClient(app)
    client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    yield client, engine
    app.dependency_overrides.clear()


def _d(days_ago: int) -> dt.date:
    return TODAY - dt.timedelta(days=days_ago)


def _seed_full(engine) -> None:
    """Засеять по одной записи во все источники сигналов в пределах окна 90 дней."""
    with Session(engine) as s:
        # Цель: вес 75, %жира 15, обхват талии 80.
        s.add(
            SmartGoal(
                user_id=1,
                target_weight_kg=75.0,
                target_body_fat_pct=15.0,
                target_measurements_json={"waist": 80},
                why_notes="к лету",
                status="active",
            )
        )
        # InBody: старый (база) и свежий замер.
        s.add(InbodyMeasurement(date=_d(30), weight_kg=85.0, body_fat_pct=25.0, user_id=1))
        s.add(InbodyMeasurement(date=_d(5), weight_kg=80.0, body_fat_pct=22.0, user_id=1))
        # Замеры тела: талия 90 → 85.
        s.add(BodyMeasurement(date=_d(30), waist_cm=90.0, user_id=1))
        s.add(BodyMeasurement(date=_d(5), waist_cm=85.0, user_id=1))
        # Питание: два дня.
        s.add(
            FoodEntry(
                user_id=1,
                date=_d(1),
                meal="Обед",
                product_name="A",
                kcal=2000,
                protein_g=150,
                fat_g=60,
                carb_g=200,
            )
        )
        s.add(
            FoodEntry(
                user_id=1,
                date=_d(2),
                meal="Обед",
                product_name="B",
                kcal=1800,
                protein_g=130,
                fat_g=50,
                carb_g=180,
            )
        )
        # Активность + дефицит.
        s.add(ActivityDay(date=_d(1), total_kcal=2500, steps=10000, moving_min=60))
        s.add(ActivityDay(date=_d(2), total_kcal=2300, steps=8000, moving_min=50))
        s.add(DeficitDay(date=_d(1), user_id=1, eaten_kcal=2000, burn_kcal=2500, deficit_kcal=500))
        s.add(DeficitDay(date=_d(2), user_id=1, eaten_kcal=1800, burn_kcal=2300, deficit_kcal=500))
        # Спорт/упражнения.
        strength_sport = Sport(name="Силовая", type=SportType.strength)
        cardio_sport = Sport(name="Бег", type=SportType.cardio)
        s.add(strength_sport)
        s.add(cardio_sport)
        s.commit()
        s.refresh(strength_sport)
        s.refresh(cardio_sport)
        press = Exercise(sport_id=strength_sport.id, name="Жим лёжа")
        run = Exercise(sport_id=cardio_sport.id, name="Бег 5к")
        s.add(press)
        s.add(run)
        s.commit()
        s.refresh(press)
        s.refresh(run)
        # Силовая сессия с двумя подходами.
        strength_session = WorkoutSession(user_id=1, sport_id=strength_sport.id, date=_d(3))
        s.add(strength_session)
        s.commit()
        s.refresh(strength_session)
        s.add(
            StrengthSet(session_id=strength_session.id, exercise_id=press.id, weight_kg=100, reps=5)
        )
        s.add(
            StrengthSet(session_id=strength_session.id, exercise_id=press.id, weight_kg=90, reps=8)
        )
        # Кардио сессия.
        cardio_session = WorkoutSession(user_id=1, sport_id=cardio_sport.id, date=_d(4))
        s.add(cardio_session)
        s.commit()
        s.refresh(cardio_session)
        s.add(
            CardioLog(
                session_id=cardio_session.id,
                exercise_id=run.id,
                distance_km=5.0,
                duration_sec=1500,
                avg_hr=150,
            )
        )
        # PR: текущий рекорд по жиму перебивает старый.
        s.add(
            PersonalRecord(
                user_id=1,
                exercise_id=press.id,
                metric="max_weight",
                date=_d(20),
                value=95,
                unit="кг",
            )
        )
        s.add(
            PersonalRecord(
                user_id=1,
                exercise_id=press.id,
                metric="max_weight",
                date=_d(3),
                value=100,
                unit="кг",
            )
        )
        s.commit()


def test_empty_db_builds_full_resilient_snapshot(ctx):
    """Пустая БД: снапшот собирается целиком, пустые секции — null/пусто/0."""
    _, engine = ctx
    with Session(engine) as s:
        snap = snapshot_service.build_snapshot(s, end=TODAY)

    assert set(snap) == {
        "generated_at",
        "window",
        "goal",
        "nutrition",
        "activity",
        "measurements",
        "inbody",
        "training",
        "personal_records",
    }
    assert snap["goal"] is None
    assert snap["nutrition"] == {
        "logged_days": 0,
        "avg_kcal_in": None,
        "avg_protein_g": None,
        "avg_fat_g": None,
        "avg_carb_g": None,
        "recent": {
            "days": 0,
            "avg_kcal_in": None,
            "avg_protein_g": None,
            "avg_fat_g": None,
            "avg_carb_g": None,
        },
    }
    assert snap["activity"]["logged_days"] == 0
    assert snap["activity"]["deficit"] == {
        "complete_days": 0,
        "avg_deficit_kcal": None,
        "total_deficit_kcal": None,
    }
    assert snap["measurements"] == {"latest_date": None, "values": {}}
    assert snap["inbody"] is None
    assert snap["training"] == {"sessions": 0, "by_sport": [], "strength": [], "cardio": []}
    assert snap["personal_records"] == []


def test_full_snapshot_has_all_signals(ctx):
    """Засеяны все источники: каждая секция несёт ожидаемые агрегаты."""
    _, engine = ctx
    _seed_full(engine)
    with Session(engine) as s:
        snap = snapshot_service.build_snapshot(s, end=TODAY)

    # Цель + прогресс по трём метрикам.
    goal = snap["goal"]
    assert goal["target_weight_kg"] == 75.0
    progress = {m["metric"]: m for m in goal["progress"]}
    assert progress["weight_kg"] == {
        "metric": "weight_kg",
        "target": 75.0,
        "baseline": 85.0,
        "current": 80.0,
        "remaining": 5.0,
        "percent": 50.0,
    }
    assert progress["body_fat_pct"]["percent"] == 30.0
    assert progress["waist_cm"]["current"] == 85.0
    assert progress["waist_cm"]["percent"] == 50.0

    # Питание: средние по двум дням.
    assert snap["nutrition"]["logged_days"] == 2
    assert snap["nutrition"]["avg_kcal_in"] == 1900.0
    assert snap["nutrition"]["recent"]["days"] == 2

    # Активность + дефицит.
    assert snap["activity"]["avg_steps"] == 9000.0
    assert snap["activity"]["deficit"] == {
        "complete_days": 2,
        "avg_deficit_kcal": 500.0,
        "total_deficit_kcal": 1000,
    }

    # Замеры тела и InBody с динамикой.
    assert snap["measurements"]["values"]["waist_cm"] == {"current": 85.0, "change": -5.0}
    assert snap["inbody"]["values"]["weight_kg"] == {"current": 80.0, "change": -5.0}
    assert snap["inbody"]["values"]["body_fat_pct"] == {"current": 22.0, "change": -3.0}

    # Тренировки: силовые + кардио.
    assert snap["training"]["sessions"] == 2
    strength = snap["training"]["strength"][0]
    assert strength["exercise_name"] == "Жим лёжа"
    assert strength["latest_working_weight"] == 100.0
    assert strength["best_1rm"] == 116.67  # epley(100,5)
    assert strength["total_tonnage"] == 1220.0  # 100*5 + 90*8
    cardio = snap["training"]["cardio"][0]
    assert cardio["total_distance_km"] == 5.0
    assert cardio["avg_pace_sec_km"] == 300.0  # 1500с / 5км
    assert cardio["avg_hr"] == 150.0

    # PR: остаётся лучший (100), а не старый (95).
    assert snap["personal_records"] == [
        {
            "exercise_id": strength["exercise_id"],
            "exercise_name": "Жим лёжа",
            "metric": "max_weight",
            "value": 100.0,
            "unit": "кг",
            "date": _d(3).isoformat(),
        }
    ]


def test_goal_without_measurements_is_resilient(ctx):
    """Цель есть, замеров нет: прогресс отдаёт None, а не падает."""
    _, engine = ctx
    with Session(engine) as s:
        s.add(SmartGoal(user_id=1, target_weight_kg=75.0, status="active"))
        s.commit()
        snap = snapshot_service.build_snapshot(s, end=TODAY)
    metric = snap["goal"]["progress"][0]
    assert metric["metric"] == "weight_kg"
    assert metric["current"] is None
    assert metric["percent"] is None
    assert metric["target"] == 75.0


def test_snapshot_route_requires_auth():
    """Роут под сессией: без входа — 401."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        resp = TestClient(app).get("/snapshot")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_snapshot_route_returns_json(ctx):
    """GET /snapshot под сессией отдаёт собранный объект со всеми секциями."""
    client, engine = ctx
    _seed_full(engine)
    resp = client.get("/snapshot")
    assert resp.status_code == 200
    body = resp.json()
    assert body["goal"]["target_weight_kg"] == 75.0
    assert body["window"]["days"] == 90
    assert {
        "nutrition",
        "activity",
        "measurements",
        "inbody",
        "training",
        "personal_records",
    } <= set(body)


def test_snapshot_route_window_days_param(ctx):
    """window_days сужает окно: старые точки выпадают из сводок."""
    client, engine = ctx
    _seed_full(engine)
    # Окно 3 дня (end=сегодня): тренировки (3-4 дня назад) и старые замеры выпадают.
    resp = client.get("/snapshot", params={"window_days": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert body["window"]["days"] == 3
    assert body["training"]["sessions"] == 0
    # Питание за 1-2 дня назад остаётся.
    assert body["nutrition"]["logged_days"] == 2
