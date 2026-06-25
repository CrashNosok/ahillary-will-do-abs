"""Правило закрытия ачивки (S5.5): unlocked возможен лишь при наличии видео-пруфа.

Закрывает критерии карточки:
- попытка закрыть ачивку без achievement_proof → отказ (409), статус остаётся как был,
  unlocked_at не проставляется;
- при наличии хотя бы одного пруфа → статус unlocked и unlocked_at проставлен.
Плюс: неизвестная ачивка → 404, повторное закрытие сохраняет исходный unlocked_at,
роут под авторизацией.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401 — регистрирует таблицы в SQLModel.metadata
from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.achievement import Achievement, AchievementProof
from app.models.user import User

EMAIL = "unlock@example.com"
PASSWORD = "right-password"


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(eng)
    with Session(eng) as session:
        session.add(User(email=EMAIL, password_hash=hash_password(PASSWORD)))
        session.add(
            Achievement(id=1, user_id=1, sport_id=None, title="Первый подтяг", status="in_progress")
        )
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


def _add_proof(engine, achievement_id: int = 1) -> None:
    with Session(engine) as session:
        session.add(
            AchievementProof(
                achievement_id=achievement_id,
                video_path=f"data/videos/{achievement_id}/x.mp4",
                thumbnail_path=f"data/videos/{achievement_id}/x.jpg",
            )
        )
        session.commit()


def _fetch(engine, achievement_id: int = 1) -> Achievement:
    with Session(engine) as session:
        return session.get(Achievement, achievement_id)


def test_unlock_without_proof_is_rejected(client, engine):
    # критерий: попытка закрыть без видео → отказ; статус и unlocked_at не меняются
    resp = client.post("/achievements/1/unlock")
    assert resp.status_code == 409
    assert "пруф" in resp.json()["detail"].lower() or "видео" in resp.json()["detail"].lower()

    after = _fetch(engine)
    assert after.status == "in_progress"
    assert after.unlocked_at is None


def test_unlock_with_proof_sets_unlocked_and_timestamp(client, engine):
    # критерий: с видео → статус unlocked, unlocked_at проставлен
    _add_proof(engine)

    resp = client.post("/achievements/1/unlock")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "unlocked"
    assert body["unlocked_at"] is not None

    after = _fetch(engine)
    assert after.status == "unlocked"
    assert after.unlocked_at is not None


def test_unlock_is_idempotent_keeps_first_timestamp(client, engine):
    # повторное закрытие не перетирает исходный момент закрытия
    _add_proof(engine)
    first = client.post("/achievements/1/unlock").json()["unlocked_at"]
    second = client.post("/achievements/1/unlock")
    assert second.status_code == 200
    assert second.json()["unlocked_at"] == first


def test_unlock_unknown_achievement_returns_404(client):
    resp = client.post("/achievements/999/unlock")
    assert resp.status_code == 404
    assert "не найден" in resp.json()["detail"].lower()


def test_unlock_requires_auth(engine):
    app.dependency_overrides.clear()
    assert TestClient(app).post("/achievements/1/unlock").status_code == 401
