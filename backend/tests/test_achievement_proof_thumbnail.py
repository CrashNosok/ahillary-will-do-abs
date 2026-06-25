"""Отдача превью видео-пруфа ачивки (S5.6 UI): GET .../proof/thumbnail.

Карточка S5.6 требует «превью показывается в карточке ачивки» — фронт берёт картинку
по этому маршруту. Нет пруфа / файла нет на диске → 404; есть пруф → 200 image/jpeg
с байтами файла. Роут под авторизацией.
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

EMAIL = "thumb@example.com"
PASSWORD = "right-password"
JPEG = b"\xff\xd8\xff\xe0fake-jpeg-bytes"


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(eng)
    with Session(eng) as session:
        session.add(User(email=EMAIL, password_hash=hash_password(PASSWORD)))
        session.add(Achievement(id=1, user_id=1, sport_id=None, title="Первый подтяг"))
        session.commit()
    return eng


@pytest.fixture
def client(engine):
    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    c = TestClient(app)
    c.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    yield c
    app.dependency_overrides.clear()


def _add_proof(engine, thumbnail_path: str, achievement_id: int = 1) -> None:
    with Session(engine) as session:
        session.add(
            AchievementProof(
                achievement_id=achievement_id,
                video_path=f"data/videos/{achievement_id}/x.mp4",
                thumbnail_path=thumbnail_path,
            )
        )
        session.commit()


def test_thumbnail_404_without_proof(client):
    assert client.get("/achievements/1/proof/thumbnail").status_code == 404


def test_thumbnail_returns_jpeg(client, engine, tmp_path):
    thumb = tmp_path / "thumb.jpg"
    thumb.write_bytes(JPEG)
    _add_proof(engine, str(thumb))

    resp = client.get("/achievements/1/proof/thumbnail")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/jpeg")
    assert resp.content == JPEG


def test_thumbnail_404_when_file_missing(client, engine, tmp_path):
    _add_proof(engine, str(tmp_path / "gone.jpg"))
    assert client.get("/achievements/1/proof/thumbnail").status_code == 404


def test_thumbnail_unknown_achievement_404(client):
    assert client.get("/achievements/999/proof/thumbnail").status_code == 404


def test_thumbnail_requires_auth(engine):
    app.dependency_overrides.clear()
    assert TestClient(app).get("/achievements/1/proof/thumbnail").status_code == 401
