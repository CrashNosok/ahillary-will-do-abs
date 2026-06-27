"""Реестр метрик + единая карта целей (services/metrics.py).

Закрывает: легаси-ключи целей приводятся к колонкам БД (hips→glutes_cm — иначе цель
терялась); target_metrics_json — источник правды и перекрывает легаси; неизвестные ключи
отбрасываются; каждая метрика тела имеет column == key (резолверы полагаются на это).
"""

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401 — регистрирует все таблицы в metadata
from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.activity import ActivityDay
from app.models.body import BodyMeasurement, InbodyMeasurement
from app.models.deficit import DeficitDay
from app.models.goal import SmartGoal
from app.models.nutrition import FoodEntry
from app.models.user import User
from app.services.metrics import (
    GROUP_DAILY,
    REGISTRY,
    current_metric_values,
    effective_targets,
    metrics_by_group,
    resolve_metric,
)

TODAY = dt.date(2026, 6, 27)


def _seed_metrics(session: Session) -> None:
    """Свои данные (user_id=1) + чужие (user_id=2, не должны попасть в выборку)."""
    session.add(User(email="cur@example.com", password_hash=hash_password("pw")))  # id=1
    session.add(User(email="other@example.com", password_hash="x"))  # id=2
    # Тело: берём последний не-null замер за окно.
    session.add(InbodyMeasurement(user_id=1, date=TODAY - dt.timedelta(days=10), weight_kg=92.0))
    session.add(
        InbodyMeasurement(
            user_id=1, date=TODAY - dt.timedelta(days=2), weight_kg=90.0, body_fat_pct=18.0
        )
    )
    session.add(BodyMeasurement(user_id=1, date=TODAY - dt.timedelta(days=1), waist_cm=85.0))
    # Дневные: среднее за окно.
    session.add(
        FoodEntry(
            user_id=1, date=TODAY, meal="Обед", product_name="x", kcal=2000, protein_g=150
        )
    )
    session.add(
        FoodEntry(
            user_id=1,
            date=TODAY - dt.timedelta(days=1),
            meal="Обед",
            product_name="y",
            kcal=2200,
            protein_g=130,
        )
    )
    session.add(ActivityDay(user_id=1, date=TODAY, steps=8000))
    session.add(ActivityDay(user_id=1, date=TODAY - dt.timedelta(days=1), steps=10000))
    session.add(DeficitDay(user_id=1, date=TODAY, deficit_kcal=400))
    # Чужое — не должно повлиять.
    session.add(InbodyMeasurement(user_id=2, date=TODAY, weight_kg=70.0))
    session.commit()


def test_body_metrics_column_equals_key():
    # резолверы прогресса берут getattr(model, spec.column) — column обязан == key
    for spec in REGISTRY:
        if spec.model is not None:
            assert spec.column == spec.key
        else:
            assert spec.is_daily and spec.daily_source is not None


def test_effective_targets_from_metrics_json_filters_unknown():
    # источник правды — target_metrics_json; неизвестные реестру ключи отбрасываются
    goal = SmartGoal(
        user_id=1,
        target_metrics_json={"weight_kg": 75.0, "glutes_cm": 95.0, "steps": 10000.0, "nope": 1.0},
    )
    targets = effective_targets(goal)
    assert targets == {"weight_kg": 75.0, "glutes_cm": 95.0, "steps": 10000.0}


def test_effective_targets_empty_when_no_goal_or_no_targets():
    assert effective_targets(None) == {}
    assert effective_targets(SmartGoal(user_id=1)) == {}


def test_daily_group_has_no_model():
    for spec in metrics_by_group(GROUP_DAILY):
        assert spec.model is None and spec.column is None


def test_resolve_unknown_is_none():
    assert resolve_metric("height_cm") is None  # рост целью не является
    assert resolve_metric("nope") is None


def test_current_metric_values_body_latest_and_daily_avg():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_metrics(session)
        out = current_metric_values(session, user_id=1, today=TODAY)

    assert out["weight_kg"] == 90.0  # последний не-null замер, а не самый старый/чужой
    assert out["body_fat_pct"] == 18.0
    assert out["waist_cm"] == 85.0
    assert out["kcal_in"] == 2100.0  # среднесуточное (2000+2200)/2
    assert out["protein_g"] == 140.0
    assert out["steps"] == 9000.0
    assert out["deficit_kcal"] == 400.0
    assert "muscle_mass_kg" not in out  # нет данных — метрика опущена (не ложный 0)


def test_get_current_metrics_endpoint_returns_map():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_metrics(session)

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        client = TestClient(app)
        client.post("/auth/login", json={"email": "cur@example.com", "password": "pw"})
        resp = client.get("/metrics/current")
        assert resp.status_code == 200
        body = resp.json()
        assert body["weight_kg"] == 90.0
        assert body["steps"] == 9000.0
    finally:
        app.dependency_overrides.clear()


def test_get_current_metrics_requires_auth():
    app.dependency_overrides.clear()
    assert TestClient(app).get("/metrics/current").status_code == 401
