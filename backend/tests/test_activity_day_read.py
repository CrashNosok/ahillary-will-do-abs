"""GET /import/activity/{date} — чтение дня активности для предзаполнения попапа дня.

Закрывает: после ручного ввода форма «Изменить» должна показать ранее внесённые поля.
- день есть → 200 с восемью метриками;
- дня нет → 200 c null (без 4xx-шума при открытии пустого дня);
- чужой день не виден (изоляция M0·B7);
- роут под авторизацией.
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
from app.models.user import User

EMAIL = "dayread@example.com"
PASSWORD = "right-password"
OTHER_EMAIL = "other@example.com"


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
    from sqlmodel import select

    with Session(engine) as session:
        return session.exec(select(User).where(User.email == email)).one().id


def test_returns_saved_day(client, engine):
    # критерий: ранее внесённые метрики читаются обратно для предзаполнения формы
    client.post(
        "/import/activity/manual",
        json={"date": "2026-06-20", "total_kcal": 1218, "active_kcal": 683, "steps": 4459},
    )
    resp = client.get("/import/activity/2026-06-20")
    assert resp.status_code == 200
    body = resp.json()
    assert body is not None
    assert body["total_kcal"] == 1218 and body["active_kcal"] == 683 and body["steps"] == 4459


def test_missing_day_returns_null_200(client):
    # пустой день — 200 с null, без 4xx-шума при открытии формы
    resp = client.get("/import/activity/2026-01-01")
    assert resp.status_code == 200
    assert resp.json() is None


def test_other_users_day_not_visible(client, engine):
    # изоляция (M0·B7): чужой день не виден владельцу сессии — отдаём null
    other_id = _user_id(engine, OTHER_EMAIL)
    with Session(engine) as session:
        session.add(ActivityDay(user_id=other_id, date=dt.date(2026, 6, 20), total_kcal=999))
        session.commit()
    resp = client.get("/import/activity/2026-06-20")
    assert resp.status_code == 200
    assert resp.json() is None


def test_requires_auth(engine):
    app.dependency_overrides.clear()
    resp = TestClient(app).get("/import/activity/2026-06-20")
    assert resp.status_code == 401
