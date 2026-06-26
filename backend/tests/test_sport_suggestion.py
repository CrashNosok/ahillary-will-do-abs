"""Заявки «предложить вид спорта» (POST/GET /sports/suggestions): создание со status=pending,
пустое имя → 422, список скоуплен по пользователю."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401 — регистрирует таблицы в SQLModel.metadata
from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.user import User

PW = "right-password"


@pytest.fixture
def engine():
    return create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )


def _client(engine, email):
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        if not s.get(User, 1):
            s.add(User(email=email, password_hash=hash_password(PW)))
            s.commit()

    def override():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = override
    c = TestClient(app)
    c.post("/auth/login", json={"email": email, "password": PW})
    return c


def test_create_suggestion_pending(engine):
    c = _client(engine, "a@x.com")
    res = c.post(
        "/sports/suggestions",
        json={"name": "Сквош", "category": "racket", "note": "нет в каталоге"},
    )
    assert res.status_code == 201, res.text
    b = res.json()
    assert b["name"] == "Сквош" and b["category"] == "racket" and b["status"] == "pending"
    # появляется в своём списке
    assert any(s["name"] == "Сквош" for s in c.get("/sports/suggestions").json())
    app.dependency_overrides.clear()


def test_empty_name_rejected(engine):
    c = _client(engine, "b@x.com")
    assert c.post("/sports/suggestions", json={"name": "   "}).status_code == 422
    app.dependency_overrides.clear()
