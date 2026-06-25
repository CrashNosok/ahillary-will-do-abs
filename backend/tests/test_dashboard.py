"""Дашборд API: дневные флаги данных + текущий стрик логирования (S1.13).

Закрывает критерии карточки:
- флаги has_food/has_activity/has_training/has_measurement верны на данных (и пусты
  на чистой БД — «сид-данные» без логов);
- стрик «еда+активность» считается корректно, включая разрыв и грейс на сегодня.
"""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401 — регистрирует таблицы в SQLModel.metadata
from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.activity import ActivityDay
from app.models.body import BodyMeasurement, InbodyMeasurement, ProgressPhoto
from app.models.nutrition import FoodEntry
from app.models.user import User
from app.models.workout import WorkoutSession
from app.services import dashboard

EMAIL = "dash@example.com"
PASSWORD = "right-password"


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _food(session, date, kcal=100.0):
    session.add(FoodEntry(user_id=1, date=date, meal="Обед", product_name="x", kcal=kcal))
    session.commit()


def _activity(session, date, total_kcal=500):
    session.add(ActivityDay(date=date, total_kcal=total_kcal))
    session.commit()


def _training(session, date):
    session.add(WorkoutSession(user_id=1, date=date, title="т"))
    session.commit()


# ── флаги ─────────────────────────────────────────────────────────────────


def test_flags_empty_db_all_false(session):
    # «сид-данные»: пользователь есть, логов нет → все флаги False, дни покрывают диапазон
    start, end = dt.date(2026, 6, 1), dt.date(2026, 6, 3)
    days = dashboard.day_flags(start, end, session)
    assert [d.date for d in days] == [
        dt.date(2026, 6, 1),
        dt.date(2026, 6, 2),
        dt.date(2026, 6, 3),
    ]
    assert all(
        not (d.has_food or d.has_activity or d.has_training or d.has_measurement) for d in days
    )


def test_flags_reflect_each_source(session):
    day = dt.date(2026, 6, 10)
    _food(session, day)
    _activity(session, day)
    _training(session, day)
    session.add(BodyMeasurement(date=day, waist_cm=80, user_id=1))
    session.commit()

    [d] = dashboard.day_flags(day, day, session)
    assert (d.has_food, d.has_activity, d.has_training, d.has_measurement) == (
        True,
        True,
        True,
        True,
    )


def test_measurement_flag_covers_inbody(session):
    day = dt.date(2026, 6, 11)
    session.add(InbodyMeasurement(date=day, weight_kg=90, user_id=1))
    session.commit()
    [d] = dashboard.day_flags(day, day, session)
    assert d.has_measurement is True
    assert d.has_food is False


def test_weekly_flags_split_weight_body_photo(session):
    # Недельные категории раздельны: вес(inbody)/замеры(body)/фото — каждый сам по себе.
    w, b, p = dt.date(2026, 6, 1), dt.date(2026, 6, 2), dt.date(2026, 6, 3)
    session.add(InbodyMeasurement(date=w, weight_kg=88, user_id=1))
    session.add(BodyMeasurement(date=b, waist_cm=80, user_id=1))
    session.add(ProgressPhoto(date=p, source_image_path="x.jpg", user_id=1))
    session.commit()

    days = {d.date: d for d in dashboard.day_flags(w, p, session)}
    assert (days[w].has_weight, days[w].has_body, days[w].has_photo) == (True, False, False)
    assert (days[b].has_weight, days[b].has_body, days[b].has_photo) == (False, True, False)
    assert (days[p].has_weight, days[p].has_body, days[p].has_photo) == (False, False, True)
    # легаси has_measurement = body|inbody (фото в него не входит)
    assert days[w].has_measurement and days[b].has_measurement and not days[p].has_measurement


def test_flags_isolated_per_day(session):
    _food(session, dt.date(2026, 6, 1))
    _activity(session, dt.date(2026, 6, 2))
    rows = dashboard.day_flags(dt.date(2026, 6, 1), dt.date(2026, 6, 2), session)
    days = {d.date: d for d in rows}
    assert days[dt.date(2026, 6, 1)].has_food and not days[dt.date(2026, 6, 1)].has_activity
    assert days[dt.date(2026, 6, 2)].has_activity and not days[dt.date(2026, 6, 2)].has_food


def test_flags_reject_inverted_range(session):
    with pytest.raises(ValueError):
        dashboard.day_flags(dt.date(2026, 6, 3), dt.date(2026, 6, 1), session)


# ── стрик ─────────────────────────────────────────────────────────────────


def _complete(session, date):
    _food(session, date)
    _activity(session, date)


def test_streak_counts_consecutive_complete_days(session):
    today = dt.date(2026, 6, 10)
    for d in (today, today - dt.timedelta(days=1), today - dt.timedelta(days=2)):
        _complete(session, d)
    assert dashboard.current_streak(session, today=today) == 3


def test_streak_breaks_on_gap(session):
    today = dt.date(2026, 6, 10)
    _complete(session, today)
    _complete(session, today - dt.timedelta(days=1))
    # пропуск на today-2 (нет данных) → серия обрывается на 2
    _complete(session, today - dt.timedelta(days=3))
    assert dashboard.current_streak(session, today=today) == 2


def test_streak_needs_both_food_and_activity(session):
    today = dt.date(2026, 6, 10)
    _food(session, today)  # только еда, активности нет → день не «полный»
    assert dashboard.current_streak(session, today=today) == 0


def test_streak_grace_for_unlogged_today(session):
    # сегодня ещё не закрыт, но серия до вчера идёт — не штрафуем за незавершённый день
    today = dt.date(2026, 6, 10)
    _complete(session, today - dt.timedelta(days=1))
    _complete(session, today - dt.timedelta(days=2))
    assert dashboard.current_streak(session, today=today) == 2


def test_streak_zero_when_yesterday_also_missing(session):
    today = dt.date(2026, 6, 10)
    _complete(session, today - dt.timedelta(days=2))  # позавчера полный, но вчера и сегодня нет
    assert dashboard.current_streak(session, today=today) == 0


# ── сводка дня ────────────────────────────────────────────────────────────


def test_today_summary_empty_is_zero(session):
    s = dashboard.today_summary(session, today=dt.date(2026, 6, 21))
    assert (s.kcal_in, s.kcal_out, s.deficit) == (0, 0, 0)


def test_today_summary_sums_food_and_reads_activity(session):
    today = dt.date(2026, 6, 21)
    _food(session, today, kcal=600)
    _food(session, today, kcal=750)
    _activity(session, today, total_kcal=2100)
    s = dashboard.today_summary(session, today=today)
    assert s.kcal_in == 1350
    assert s.kcal_out == 2100
    assert s.deficit == 750  # потрачено − съедено


def test_today_summary_surplus_is_negative(session):
    today = dt.date(2026, 6, 21)
    _food(session, today, kcal=3000)
    _activity(session, today, total_kcal=2000)
    assert dashboard.today_summary(session, today=today).deficit == -1000


def test_today_summary_ignores_other_days(session):
    today = dt.date(2026, 6, 21)
    _food(session, today - dt.timedelta(days=1), kcal=999)
    _activity(session, today - dt.timedelta(days=1), total_kcal=999)
    s = dashboard.today_summary(session, today=today)
    assert (s.kcal_in, s.kcal_out) == (0, 0)


# ── эндпоинт ──────────────────────────────────────────────────────────────


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(User(email=EMAIL, password_hash=hash_password(PASSWORD)))
        today = dt.date.today()
        s.add(FoodEntry(user_id=1, date=today, meal="Обед", product_name="x", kcal=100))
        s.add(ActivityDay(date=today, total_kcal=500))
        s.commit()

    def override_get_session():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = override_get_session
    c = TestClient(app)
    c.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    yield c
    app.dependency_overrides.clear()


def test_dashboard_endpoint_returns_flags_and_streak(client):
    today = dt.date.today()
    resp = client.get("/dashboard", params={"start": str(today), "end": str(today)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["current_streak"] == 1
    assert len(body["days"]) == 1
    d = body["days"][0]
    assert d["date"] == str(today)
    assert d["has_food"] and d["has_activity"]
    assert not d["has_training"] and not d["has_measurement"]


def test_dashboard_endpoint_includes_today_summary(client):
    # фикстура клиента кладёт на сегодня еду 100 ккал и активность 500 ккал
    today = dt.date.today()
    resp = client.get("/dashboard", params={"start": str(today), "end": str(today)})
    assert resp.status_code == 200
    t = resp.json()["today"]
    assert t["date"] == str(today)
    assert t["kcal_in"] == 100
    assert t["kcal_out"] == 500
    assert t["deficit"] == 400


def test_dashboard_inverted_range_is_422(client):
    resp = client.get("/dashboard", params={"start": "2026-06-10", "end": "2026-06-01"})
    assert resp.status_code == 422


def test_dashboard_requires_auth():
    app.dependency_overrides.clear()
    assert TestClient(app).get("/dashboard").status_code == 401
