"""Progress API (S2.4): временные ряды веса (InBody) и обхватов (body) по датам.

Закрывает критерий карточки: ряды по датам отдаются для выбранного периода.
Вес берём из inbody_measurement (нет HTTP-CRUD — пишем в БД напрямую), обхваты —
из body_measurement (создаём через HTTP). Период фильтруется по [start; end].
"""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.body import InbodyMeasurement
from app.models.user import User

EMAIL = "progress@example.com"
PASSWORD = "right-password"


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


def _add_inbody(engine, date: str, weight_kg: float | None) -> None:
    with Session(engine) as session:
        session.add(InbodyMeasurement(date=dt.date.fromisoformat(date), weight_kg=weight_kg))
        session.commit()


def test_weight_series_chronological(ctx):
    client, engine = ctx
    for date, w in (("2026-06-21", 80.0), ("2026-05-24", 82.5), ("2026-06-07", 81.0)):
        _add_inbody(engine, date, w)
    resp = client.get("/progress/body", params={"start": "2026-05-01", "end": "2026-06-30"})
    assert resp.status_code == 200
    weight = resp.json()["weight_kg"]
    assert [p["date"] for p in weight] == ["2026-05-24", "2026-06-07", "2026-06-21"]
    assert [p["value"] for p in weight] == [82.5, 81.0, 80.0]


def test_circumference_series_by_date(ctx):
    client, _ = ctx
    client.post("/body-measurements", json={"date": "2026-06-07", "waist_cm": 84})
    client.post("/body-measurements", json={"date": "2026-06-21", "waist_cm": 82})
    resp = client.get("/progress/body", params={"start": "2026-06-01", "end": "2026-06-30"})
    assert resp.status_code == 200
    waist = resp.json()["circumferences"]["waist_cm"]
    assert waist == [
        {"date": "2026-06-07", "value": 84},
        {"date": "2026-06-21", "value": 82},
    ]


def test_period_filter_excludes_out_of_range(ctx):
    client, engine = ctx
    _add_inbody(engine, "2026-01-01", 90.0)  # вне периода
    _add_inbody(engine, "2026-06-10", 80.0)  # внутри
    client.post("/body-measurements", json={"date": "2026-01-01", "waist_cm": 95})  # вне
    client.post("/body-measurements", json={"date": "2026-06-10", "waist_cm": 82})  # внутри
    resp = client.get("/progress/body", params={"start": "2026-06-01", "end": "2026-06-30"})
    body = resp.json()
    assert [p["date"] for p in body["weight_kg"]] == ["2026-06-10"]
    assert [p["date"] for p in body["circumferences"]["waist_cm"]] == ["2026-06-10"]


def test_null_values_skipped(ctx):
    client, engine = ctx
    _add_inbody(engine, "2026-06-10", None)  # вес не заполнен — не точка ряда
    _add_inbody(engine, "2026-06-11", 80.0)
    client.post("/body-measurements", json={"date": "2026-06-10", "chest_cm": 100})  # без waist
    resp = client.get("/progress/body", params={"start": "2026-06-01", "end": "2026-06-30"})
    body = resp.json()
    assert [p["date"] for p in body["weight_kg"]] == ["2026-06-11"]
    assert body["circumferences"]["waist_cm"] == []
    assert [p["date"] for p in body["circumferences"]["chest_cm"]] == ["2026-06-10"]


def test_default_range_returns_recent(ctx):
    client, engine = ctx
    today = dt.date.today().isoformat()
    _add_inbody(engine, today, 79.0)
    resp = client.get("/progress/body")  # без параметров — дефолтный период
    assert resp.status_code == 200
    body = resp.json()
    assert body["end"] == today
    assert [p["date"] for p in body["weight_kg"]] == [today]


def test_start_after_end_returns_422(ctx):
    client, _ = ctx
    resp = client.get("/progress/body", params={"start": "2026-06-30", "end": "2026-06-01"})
    assert resp.status_code == 422


def test_requires_auth():
    app.dependency_overrides.clear()
    assert TestClient(app).get("/progress/body").status_code == 401
