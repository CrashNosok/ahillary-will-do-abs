"""Auth: login выдаёт подписанную HttpOnly cookie, guard 401-ит без валидной сессии.

Закрывает критерии S0.7: неверный пароль → 401, защищённый роут без cookie → 401,
после login cookie HttpOnly выставлен.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.db import get_session
from app.core.security import hash_password
from app.core.session import sign, unsign
from app.main import app
from app.models.user import User

EMAIL = "auth@example.com"
PASSWORD = "right-password"


@pytest.fixture
def client():
    # Изолированная in-memory БД с единственным сид-юзером; StaticPool держит одно
    # соединение, поэтому данные живут между сессиями запроса.
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
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_login_wrong_password_returns_401(client):
    resp = client.post("/auth/login", json={"email": EMAIL, "password": "wrong"})
    assert resp.status_code == 401  # критерий: неверный пароль → 401


def test_login_unknown_email_returns_401(client):
    resp = client.post("/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})
    assert resp.status_code == 401


def test_login_sets_httponly_signed_cookie(client):
    resp = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert resp.status_code == 200
    assert resp.json()["email"] == EMAIL
    set_cookie = resp.headers["set-cookie"].lower()
    assert "httponly" in set_cookie  # критерий: cookie HttpOnly выставлен
    assert "session=" in set_cookie


def test_protected_route_without_cookie_returns_401(client):
    resp = client.get("/auth/me")
    assert resp.status_code == 401  # критерий: защищённый роут без cookie → 401


def test_protected_route_with_session_returns_user(client):
    client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    resp = client.get("/auth/me")  # TestClient переносит cookie между запросами
    assert resp.status_code == 200
    assert resp.json()["email"] == EMAIL


def test_logout_invalidates_session(client):
    client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    client.post("/auth/logout")
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_protected_route_with_tampered_cookie_returns_401(client):
    client.cookies.set("session", "1.deadbeef")  # подпись не сходится
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_sign_roundtrips_and_rejects_tampering():
    signed = sign("42")
    assert unsign(signed) == "42"
    assert unsign("42.deadbeef") is None  # битая подпись
    assert unsign("42") is None  # нет подписи
