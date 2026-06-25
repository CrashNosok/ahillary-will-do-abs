"""M0·B11 — скоупинг ачивок и видео-пруфов по владельцу.

Залогинен user(id=1). Данные user(id=2) заведены напрямую в БД: общий каталожный
Sport (без user_id — общий), его Achievement(user_id=2) и реальный файл-превью на
диске. Проверяем, что владелец не видит и не трогает чужие ачивки:
- GET /sports/{id}/achievements — чужие ачивки в выдачу не попадают;
- POST /achievements/{id}/proofs, /unlock, GET .../proof/thumbnail для чужой ачивки → 404
  (не 403 — факт существования чужой записи не раскрываем);
- превью пишется реальным файлом, чтобы 404 был от проверки владельца, а не отсутствия файла;
- владелец видит и закрывает ровно своё.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401 — регистрирует все таблицы в SQLModel.metadata
from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.achievement import Achievement, AchievementProof
from app.models.sport import Sport
from app.models.user import User

EMAIL = "ach-scope@example.com"
PASSWORD = "right-password"
FAKE_VIDEO = b"not-a-real-video"


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def client(engine):
    with Session(engine) as session:
        session.add(User(email=EMAIL, password_hash=hash_password(PASSWORD)))  # id=1
        session.commit()

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    c = TestClient(app)
    c.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    yield c
    app.dependency_overrides.clear()


@pytest.fixture
def other(engine, tmp_path):
    """Чужой user(id=2): общий Sport + его ачивка с реальным файлом-превью на диске."""
    thumb = tmp_path / "other.jpg"
    thumb.write_bytes(b"\xff\xd8\xff\xe0jpeg")  # реальный файл — 404 должен дать owner-check
    with Session(engine) as session:
        session.add(User(email="other@example.com", password_hash=hash_password("x")))  # id=2
        sport = Sport(name="Вейкборд", type="skill", description="Катание за катером")
        session.add(sport)
        session.commit()
        session.refresh(sport)
        ach = Achievement(user_id=2, sport_id=sport.id, title="Чужой рейли", status="in_progress")
        session.add(ach)
        session.commit()
        session.refresh(ach)
        session.add(
            AchievementProof(achievement_id=ach.id, thumbnail_path=str(thumb), video_path="x.mp4")
        )
        session.commit()
        return {"sport_id": sport.id, "ach_id": ach.id}


# --- список ачивок спорта ----------------------------------------------------


def test_sport_achievements_excludes_other_user(client, other):
    # Sport общий, но ачивки user(id=2) к нему не отдаются владельцу.
    resp = client.get(f"/sports/{other['sport_id']}/achievements")
    assert resp.status_code == 200
    assert resp.json() == []


# --- мутирующие/файловые роуты по чужой ачивке -> 404 ------------------------


def test_upload_proof_to_other_achievement_404(client, other):
    resp = client.post(
        f"/achievements/{other['ach_id']}/proofs",
        files={"file": ("p.mp4", FAKE_VIDEO, "video/mp4")},
    )
    assert resp.status_code == 404


def test_unlock_other_achievement_404(client, other):
    assert client.post(f"/achievements/{other['ach_id']}/unlock").status_code == 404


def test_thumbnail_of_other_achievement_404(client, other):
    # Файл-превью реально существует → 404 здесь именно от проверки владельца.
    assert client.get(f"/achievements/{other['ach_id']}/proof/thumbnail").status_code == 404


# --- владелец видит и закрывает своё -----------------------------------------


def test_owner_sees_own_achievements_not_other(client, engine, other):
    with Session(engine) as session:
        session.add(
            Achievement(user_id=1, sport_id=other["sport_id"], title="Мой рейли", status="locked")
        )
        session.commit()

    body = client.get(f"/sports/{other['sport_id']}/achievements").json()
    assert [a["title"] for a in body] == ["Мой рейли"]  # ровно своя, без чужой


def test_owner_can_unlock_own_achievement(client, engine, other):
    with Session(engine) as session:
        own = Achievement(user_id=1, sport_id=other["sport_id"], title="Мой трюк", status="locked")
        session.add(own)
        session.commit()
        session.refresh(own)
        session.add(AchievementProof(achievement_id=own.id, thumbnail_path="t.jpg"))
        session.commit()
        own_id = own.id

    resp = client.post(f"/achievements/{own_id}/unlock")
    assert resp.status_code == 200
    assert resp.json()["status"] == "unlocked"
