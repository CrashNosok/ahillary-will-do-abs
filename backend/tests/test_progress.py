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
from app.models.activity import ActivityDay
from app.models.body import InbodyMeasurement
from app.models.deficit import DeficitDay
from app.models.nutrition import FoodEntry
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


# --- S2.5 Progress API: калории/дефицит/макросы/активность -------------------


def _add_food(engine, date: str, *, kcal=None, protein=None, fat=None, carb=None, meal="Обед"):
    with Session(engine) as session:
        session.add(
            FoodEntry(
                date=dt.date.fromisoformat(date),
                meal=meal,
                product_name="x",
                kcal=kcal,
                protein_g=protein,
                fat_g=fat,
                carb_g=carb,
            )
        )
        session.commit()


def _add_activity(engine, date: str, *, total_kcal=None, steps=None, moving_min=None):
    with Session(engine) as session:
        session.add(
            ActivityDay(
                date=dt.date.fromisoformat(date),
                total_kcal=total_kcal,
                steps=steps,
                moving_min=moving_min,
            )
        )
        session.commit()


def _add_deficit(engine, date: str, *, eaten=None, burn=None, deficit=None):
    with Session(engine) as session:
        session.add(
            DeficitDay(
                date=dt.date.fromisoformat(date),
                eaten_kcal=eaten,
                burn_kcal=burn,
                deficit_kcal=deficit,
            )
        )
        session.commit()


def test_energy_kcal_in_and_macros_summed_per_day(ctx):
    client, engine = ctx
    _add_food(engine, "2026-06-10", kcal=500, protein=30, fat=20, carb=40)
    _add_food(engine, "2026-06-10", kcal=300, protein=10, fat=5, carb=50)
    resp = client.get("/progress/energy", params={"start": "2026-06-01", "end": "2026-06-30"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["kcal_in"] == [{"date": "2026-06-10", "value": 800}]
    assert body["macros"]["protein_g"] == [{"date": "2026-06-10", "value": 40}]
    assert body["macros"]["fat_g"] == [{"date": "2026-06-10", "value": 25}]
    assert body["macros"]["carb_g"] == [{"date": "2026-06-10", "value": 90}]


def test_energy_activity_series_chronological(ctx):
    client, engine = ctx
    _add_activity(engine, "2026-06-06", total_kcal=2300, steps=6000, moving_min=90)
    _add_activity(engine, "2026-06-05", total_kcal=2500, steps=8000, moving_min=120)
    resp = client.get("/progress/energy", params={"start": "2026-06-01", "end": "2026-06-30"})
    body = resp.json()
    assert [p["date"] for p in body["kcal_out"]] == ["2026-06-05", "2026-06-06"]
    assert [p["value"] for p in body["kcal_out"]] == [2500, 2300]
    assert [p["value"] for p in body["steps"]] == [8000, 6000]
    assert [p["value"] for p in body["active_min"]] == [120, 90]


def test_energy_deficit_skips_incomplete_days(ctx):
    """Неполный день (deficit_kcal=None) не попадает в ряд — пропуски не ломают ряд."""
    client, engine = ctx
    _add_deficit(engine, "2026-06-05", eaten=2000, burn=2500, deficit=-500)
    _add_deficit(engine, "2026-06-06", eaten=1800, burn=None, deficit=None)  # неполный
    _add_deficit(engine, "2026-06-07", eaten=2100, burn=2400, deficit=-300)
    resp = client.get("/progress/energy", params={"start": "2026-06-01", "end": "2026-06-30"})
    assert resp.json()["deficit"] == [
        {"date": "2026-06-05", "value": -500},
        {"date": "2026-06-07", "value": -300},
    ]


def test_energy_missing_days_keep_series_intact(ctx):
    """Пропуск дня в середине не рвёт ряд; незаполненный макрос не даёт ложный 0."""
    client, engine = ctx
    _add_food(engine, "2026-06-10", kcal=500)  # protein не заполнен
    # 2026-06-11 — пропуск, никаких записей
    _add_food(engine, "2026-06-12", kcal=700)
    resp = client.get("/progress/energy", params={"start": "2026-06-01", "end": "2026-06-30"})
    body = resp.json()
    assert [p["date"] for p in body["kcal_in"]] == ["2026-06-10", "2026-06-12"]
    assert body["macros"]["protein_g"] == []  # ни одного значения — ряд пустой, без нулей


def test_energy_period_filter_excludes_out_of_range(ctx):
    client, engine = ctx
    _add_food(engine, "2026-01-01", kcal=999)  # вне периода
    _add_food(engine, "2026-06-10", kcal=500)  # внутри
    _add_activity(engine, "2026-01-01", total_kcal=2000)  # вне
    _add_activity(engine, "2026-06-10", total_kcal=2400)  # внутри
    resp = client.get("/progress/energy", params={"start": "2026-06-01", "end": "2026-06-30"})
    body = resp.json()
    assert [p["date"] for p in body["kcal_in"]] == ["2026-06-10"]
    assert [p["date"] for p in body["kcal_out"]] == ["2026-06-10"]


def test_energy_empty_period_returns_empty_series(ctx):
    client, _ = ctx
    resp = client.get("/progress/energy", params={"start": "2026-06-01", "end": "2026-06-30"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["kcal_in"] == []
    assert body["kcal_out"] == []
    assert body["deficit"] == []
    assert body["steps"] == []
    assert body["active_min"] == []
    assert body["macros"] == {"protein_g": [], "fat_g": [], "carb_g": []}


def test_energy_start_after_end_returns_422(ctx):
    client, _ = ctx
    resp = client.get("/progress/energy", params={"start": "2026-06-30", "end": "2026-06-01"})
    assert resp.status_code == 422


def test_energy_requires_auth():
    app.dependency_overrides.clear()
    assert TestClient(app).get("/progress/energy").status_code == 401


# --- S2.6 Progress API: прогресс к SMART-цели --------------------------------


def _add_inbody_fat(engine, date: str, body_fat_pct: float) -> None:
    with Session(engine) as session:
        session.add(InbodyMeasurement(date=dt.date.fromisoformat(date), body_fat_pct=body_fat_pct))
        session.commit()


def _metric(body, name):
    return next(m for m in body["metrics"] if m["metric"] == name)


def test_goal_no_active_goal_returns_404(ctx):
    client, _ = ctx
    assert client.get("/progress/goal").status_code == 404


def test_goal_requires_auth():
    app.dependency_overrides.clear()
    assert TestClient(app).get("/progress/goal").status_code == 401


def test_goal_weight_percent_and_linear_eta(ctx):
    """Чистый линейный кейс: −10 кг за 100 дней → процент и прогноз даты предсказуемы."""
    client, engine = ctx
    d0 = dt.date(2026, 1, 1)
    d1 = d0 + dt.timedelta(days=100)
    client.post(
        "/goals",
        json={"target_weight_kg": 80, "start_date": d0.isoformat(), "deadline": "2026-12-31"},
    )
    _add_inbody(engine, d0.isoformat(), 100.0)
    _add_inbody(engine, d1.isoformat(), 90.0)
    resp = client.get("/progress/goal")
    assert resp.status_code == 200
    m = _metric(resp.json(), "weight_kg")
    assert m["baseline"] == 100.0
    assert m["current"] == 90.0
    assert m["target"] == 80.0
    assert m["percent"] == 50.0  # (90−100)/(80−100) = 50%
    assert m["remaining"] == 10.0
    # темп −0.1 кг/день, осталось −10 → ещё 100 дней от последнего замера
    assert m["eta"] == (d1 + dt.timedelta(days=100)).isoformat()
    assert m["on_track"] is True


def test_goal_on_track_false_when_eta_after_deadline(ctx):
    client, engine = ctx
    d0 = dt.date(2026, 1, 1)
    d1 = d0 + dt.timedelta(days=100)
    client.post(
        "/goals",
        json={
            "target_weight_kg": 80,
            "start_date": d0.isoformat(),
            "deadline": (d1 + dt.timedelta(days=10)).isoformat(),
        },
    )
    _add_inbody(engine, d0.isoformat(), 100.0)
    _add_inbody(engine, d1.isoformat(), 90.0)
    m = _metric(client.get("/progress/goal").json(), "weight_kg")
    assert m["on_track"] is False  # eta = d1+100 дней позже дедлайна d1+10


def test_goal_moving_away_clamps_percent_zero_and_no_eta(ctx):
    client, engine = ctx
    d0 = dt.date(2026, 1, 1)
    d1 = d0 + dt.timedelta(days=100)
    client.post("/goals", json={"target_weight_kg": 80, "start_date": d0.isoformat()})
    _add_inbody(engine, d0.isoformat(), 100.0)
    _add_inbody(engine, d1.isoformat(), 105.0)  # вес растёт — движемся от цели
    m = _metric(client.get("/progress/goal").json(), "weight_kg")
    assert m["percent"] == 0.0
    assert m["remaining"] == 25.0
    assert m["eta"] is None
    assert m["on_track"] is None


def test_goal_overshoot_clamps_percent_100(ctx):
    client, engine = ctx
    d0 = dt.date(2026, 1, 1)
    d1 = d0 + dt.timedelta(days=100)
    client.post("/goals", json={"target_weight_kg": 80, "start_date": d0.isoformat()})
    _add_inbody(engine, d0.isoformat(), 100.0)
    _add_inbody(engine, d1.isoformat(), 75.0)  # уже ниже цели
    m = _metric(client.get("/progress/goal").json(), "weight_kg")
    assert m["percent"] == 100.0


def test_goal_metric_without_measurements_is_null(ctx):
    client, _ = ctx
    client.post("/goals", json={"target_weight_kg": 80})
    m = _metric(client.get("/progress/goal").json(), "weight_kg")
    assert m["current"] is None
    assert m["baseline"] is None
    assert m["percent"] is None
    assert m["eta"] is None
    assert m["remaining"] is None


def test_goal_baseline_json_used_as_start_anchor(ctx):
    """baseline_json@start_date — ранний якорь: процент считается от 100, а не от 90."""
    client, engine = ctx
    d0 = dt.date(2026, 1, 1)
    d1 = d0 + dt.timedelta(days=100)
    client.post(
        "/goals",
        json={
            "target_weight_kg": 80,
            "start_date": d0.isoformat(),
            "baseline_json": {"weight_kg": 100},
        },
    )
    _add_inbody(engine, d1.isoformat(), 90.0)  # единственный реальный замер
    m = _metric(client.get("/progress/goal").json(), "weight_kg")
    assert m["baseline"] == 100.0
    assert m["percent"] == 50.0  # без якоря база была бы 90 → 0%


def test_goal_body_fat_metric(ctx):
    client, engine = ctx
    d0 = dt.date(2026, 1, 1)
    d1 = d0 + dt.timedelta(days=100)
    client.post("/goals", json={"target_body_fat_pct": 15, "start_date": d0.isoformat()})
    _add_inbody_fat(engine, d0.isoformat(), 25.0)
    _add_inbody_fat(engine, d1.isoformat(), 20.0)
    m = _metric(client.get("/progress/goal").json(), "body_fat_pct")
    assert m["percent"] == 50.0  # (20−25)/(15−25) = 50%
    assert m["remaining"] == 5.0


def test_goal_circumference_key_resolves_to_cm_column(ctx):
    """Ключ цели waist → колонка waist_cm; метрика отдаётся под именем колонки."""
    client, _ = ctx
    d0 = dt.date(2026, 1, 1)
    d1 = d0 + dt.timedelta(days=100)
    client.post(
        "/goals", json={"target_measurements_json": {"waist": 80}, "start_date": d0.isoformat()}
    )
    client.post("/body-measurements", json={"date": d0.isoformat(), "waist_cm": 90})
    client.post("/body-measurements", json={"date": d1.isoformat(), "waist_cm": 85})
    m = _metric(client.get("/progress/goal").json(), "waist_cm")
    assert m["baseline"] == 90.0
    assert m["current"] == 85.0
    assert m["percent"] == 50.0  # (85−90)/(80−90) = 50%


def test_goal_unmeasurable_target_key_skipped(ctx):
    client, _ = ctx
    client.post("/goals", json={"target_measurements_json": {"hips": 90}})
    metrics = client.get("/progress/goal").json()["metrics"]
    assert all(m["metric"] != "hips" for m in metrics)  # нет колонки hips → пропущено
    assert all(m["metric"] != "hips_cm" for m in metrics)
