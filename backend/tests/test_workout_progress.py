"""Training progress API (S3.11): ряды для графиков тренировок.

Закрывает критерии карточки:
- ряды по упражнению/группе отдаются (силовая: рабочий вес / тренд 1ПМ / тоннаж
  по упражнению и по виду спорта);
- кардио-динамика во времени (дистанция / темп / пульс / пульсовая эффективность).

Данные пишем в БД напрямую (HTTP-CRUD для прогресса не нужен), читаем через API.
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
from app.models.sport import Exercise, Sport, SportType
from app.models.user import User
from app.models.workout import CardioLog, StrengthSet, WorkoutSession

EMAIL = "wprogress@example.com"
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


def _sport(engine, name: str, type_: SportType = SportType.strength) -> int:
    with Session(engine) as session:
        sp = Sport(name=name, type=type_)
        session.add(sp)
        session.commit()
        session.refresh(sp)
        return sp.id


def _exercise(engine, sport_id: int, name: str) -> int:
    with Session(engine) as session:
        ex = Exercise(sport_id=sport_id, name=name)
        session.add(ex)
        session.commit()
        session.refresh(ex)
        return ex.id


def _strength_session(engine, date: str, sets: list[tuple[int, float, int]]) -> None:
    """Силовая сессия: sets = [(exercise_id, weight_kg, reps), …]."""
    with Session(engine) as session:
        ws = WorkoutSession(user_id=1, date=dt.date.fromisoformat(date))
        session.add(ws)
        session.commit()
        session.refresh(ws)
        for eid, w, reps in sets:
            session.add(StrengthSet(session_id=ws.id, exercise_id=eid, weight_kg=w, reps=reps))
        session.commit()


def _cardio_session(
    engine,
    date: str,
    exercise_id: int | None,
    distance_km: float | None,
    duration_sec: float | None,
    avg_hr: int | None,
) -> None:
    with Session(engine) as session:
        ws = WorkoutSession(user_id=1, date=dt.date.fromisoformat(date))
        session.add(ws)
        session.commit()
        session.refresh(ws)
        session.add(
            CardioLog(
                session_id=ws.id,
                exercise_id=exercise_id,
                distance_km=distance_km,
                duration_sec=duration_sec,
                avg_hr=avg_hr,
            )
        )
        session.commit()


# --- Силовая: рабочий вес / 1ПМ / тоннаж по упражнению --------------------


def test_strength_series_by_exercise(ctx):
    client, engine = ctx
    sport_id = _sport(engine, "Силовая")
    eid = _exercise(engine, sport_id, "Жим лёжа")
    # день B позже дня A — проверим хронологию и помесячные значения
    _strength_session(engine, "2026-06-07", [(eid, 60, 10), (eid, 70, 5)])  # ton 600+350=950
    _strength_session(engine, "2026-06-21", [(eid, 80, 3)])  # ton 240

    resp = client.get("/progress/strength", params={"start": "2026-06-01", "end": "2026-06-30"})
    assert resp.status_code == 200
    body = resp.json()
    series = next(s for s in body["by_exercise"] if s["exercise_id"] == eid)

    assert series["working_weight"] == [
        {"date": "2026-06-07", "value": 70.0},
        {"date": "2026-06-21", "value": 80.0},
    ]
    # epley: 60x10=80.0, 70x5=81.67 → лучший 81.67; 80x3=88.0
    assert series["best_1rm"] == [
        {"date": "2026-06-07", "value": 81.67},
        {"date": "2026-06-21", "value": 88.0},
    ]
    assert series["tonnage"] == [
        {"date": "2026-06-07", "value": 950.0},
        {"date": "2026-06-21", "value": 240.0},
    ]


def test_strength_tonnage_by_group(ctx):
    client, engine = ctx
    sport_id = _sport(engine, "Тяга")
    e1 = _exercise(engine, sport_id, "Становая")
    e2 = _exercise(engine, sport_id, "Подтягивания с весом")
    # один день, два упражнения одной группы: 600 + 400 = 1000
    _strength_session(engine, "2026-06-10", [(e1, 60, 10), (e2, 40, 10)])

    resp = client.get("/progress/strength", params={"start": "2026-06-01", "end": "2026-06-30"})
    assert resp.status_code == 200
    by_group = resp.json()["by_group"]
    group = next(g for g in by_group if g["sport_id"] == sport_id)
    assert group["tonnage"] == [{"date": "2026-06-10", "value": 1000.0}]


def test_strength_respects_range(ctx):
    client, engine = ctx
    sport_id = _sport(engine, "Силовая")
    eid = _exercise(engine, sport_id, "Присед")
    _strength_session(engine, "2026-05-01", [(eid, 100, 5)])  # вне окна
    _strength_session(engine, "2026-06-15", [(eid, 110, 5)])  # в окне

    resp = client.get("/progress/strength", params={"start": "2026-06-01", "end": "2026-06-30"})
    assert resp.status_code == 200
    series = next(s for s in resp.json()["by_exercise"] if s["exercise_id"] == eid)
    assert [p["date"] for p in series["tonnage"]] == ["2026-06-15"]


def test_strength_start_after_end_422(ctx):
    client, _ = ctx
    resp = client.get("/progress/strength", params={"start": "2026-06-30", "end": "2026-06-01"})
    assert resp.status_code == 422


def test_strength_requires_auth():
    client = TestClient(app)
    assert client.get("/progress/strength").status_code == 401


# --- Кардио-динамика во времени ------------------------------------------


def test_cardio_dynamics_over_time(ctx):
    client, engine = ctx
    sport_id = _sport(engine, "Бег", SportType.cardio)
    eid = _exercise(engine, sport_id, "Бег 10к")
    # 10 км за 3000 c (50 мин) при пульсе 150:
    #   темп = 3000/10 = 300 сек/км
    #   эффективность = 10000 м / (150 * 3000/60 ударов) = 10000/7500 = 1.33 м/удар
    _cardio_session(engine, "2026-06-05", eid, 10.0, 3000.0, 150)
    _cardio_session(engine, "2026-06-19", eid, 12.0, 3300.0, 145)

    resp = client.get("/progress/cardio", params={"start": "2026-06-01", "end": "2026-06-30"})
    assert resp.status_code == 200
    series = next(s for s in resp.json()["by_exercise"] if s["exercise_id"] == eid)

    assert series["distance"] == [
        {"date": "2026-06-05", "value": 10.0},
        {"date": "2026-06-19", "value": 12.0},
    ]
    assert series["pace"][0] == {"date": "2026-06-05", "value": 300.0}
    assert series["avg_hr"][0] == {"date": "2026-06-05", "value": 150.0}
    assert series["efficiency"][0] == {"date": "2026-06-05", "value": 1.33}


def test_cardio_partial_metrics_skip_points(ctx):
    client, engine = ctx
    sport_id = _sport(engine, "Вело", SportType.cardio)
    eid = _exercise(engine, sport_id, "Шоссе")
    # только дистанция, без времени/пульса → есть distance, нет pace/avg_hr/efficiency
    _cardio_session(engine, "2026-06-12", eid, 30.0, None, None)

    resp = client.get("/progress/cardio", params={"start": "2026-06-01", "end": "2026-06-30"})
    series = next(s for s in resp.json()["by_exercise"] if s["exercise_id"] == eid)
    assert series["distance"] == [{"date": "2026-06-12", "value": 30.0}]
    assert series["pace"] == []
    assert series["avg_hr"] == []
    assert series["efficiency"] == []


def test_cardio_start_after_end_422(ctx):
    client, _ = ctx
    resp = client.get("/progress/cardio", params={"start": "2026-06-30", "end": "2026-06-01"})
    assert resp.status_code == 422


def test_cardio_requires_auth():
    client = TestClient(app)
    assert client.get("/progress/cardio").status_code == 401
