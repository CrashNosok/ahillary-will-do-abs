"""GET /workouts/simple?date= — простые («быстрые») логи владельца за день.

Закрывает: попап дня показывает ранее внесённые тренировки (тип/время/усилие/заметка + медиа).
- возвращает простые логи дня по возрастанию id;
- детальные сессии (kind=None) сюда не попадают;
- чужие логи не видны (изоляция M0·B8);
- роут под авторизацией.
"""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401 — регистрирует таблицы в SQLModel.metadata
from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.user import User
from app.models.workout import WorkoutSession

EMAIL = "swread@example.com"
PASSWORD = "right-password"
OTHER_EMAIL = "swother@example.com"
DAY = "2026-06-20"


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(eng)
    with Session(eng) as session:
        session.add(User(email=EMAIL, password_hash=hash_password(PASSWORD)))
        session.add(User(email=OTHER_EMAIL, password_hash=hash_password(PASSWORD)))
        session.commit()
    return eng


@pytest.fixture
def client(engine):
    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    test_client = TestClient(app)
    test_client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    yield test_client
    app.dependency_overrides.clear()


def _user_id(engine, email: str) -> int:
    with Session(engine) as session:
        return session.exec(select(User).where(User.email == email)).one().id


def _add_simple(client, *, note: str, duration: float | None = None):
    data = {"kind": "strength", "date": DAY, "note": note}
    if duration:
        data["duration_min"] = duration
    return client.post("/workouts/simple", data=data)


def test_returns_day_simple_workouts(client):
    # критерий: ранее внесённые тренировки дня читаются обратно
    assert _add_simple(client, note="День ног", duration=45).status_code == 201
    assert _add_simple(client, note="Пробежка", duration=30).status_code == 201
    resp = client.get(f"/workouts/simple?date={DAY}")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["notes"] == "День ног" and body[0]["duration_min"] == 45
    assert body[1]["notes"] == "Пробежка"
    assert body[0]["media"] == []


def test_excludes_detailed_sessions(client, engine):
    # детальная сессия (kind=None) не должна попадать в простой список
    uid = _user_id(engine, EMAIL)
    with Session(engine) as session:
        session.add(
            WorkoutSession(user_id=uid, date=dt.date.fromisoformat(DAY), title="Силовая", kind=None)
        )
        session.commit()
    _add_simple(client, note="Быстрый лог", duration=20)
    body = client.get(f"/workouts/simple?date={DAY}").json()
    assert len(body) == 1 and body[0]["notes"] == "Быстрый лог"


def test_other_users_workouts_not_visible(client, engine):
    other = _user_id(engine, OTHER_EMAIL)
    with Session(engine) as session:
        session.add(
            WorkoutSession(
                user_id=other, date=dt.date.fromisoformat(DAY), kind="strength", notes="чужое"
            )
        )
        session.commit()
    body = client.get(f"/workouts/simple?date={DAY}").json()
    assert body == []


def test_requires_auth(engine):
    app.dependency_overrides.clear()
    resp = TestClient(app).get(f"/workouts/simple?date={DAY}")
    assert resp.status_code == 401
