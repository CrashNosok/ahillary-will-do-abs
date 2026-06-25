"""Achievements API (S5.2): список ачивок по виду спорта + отдача статусов.

Закрывает критерии карточки:
- ачивки привязаны к виду спорта — список фильтруется по sport_id, чужие не попадают;
- статусы отдаются — поле status (locked/in_progress/unlocked) присутствует в ответе.

Запись набора покрыта в S5.1 (test_achievement_generator); здесь — только чтение.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.achievement import Achievement, AchievementProof
from app.models.sport import Sport
from app.models.user import User

EMAIL = "ach-api@example.com"
PASSWORD = "right-password"


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(eng)
    with Session(eng) as session:
        session.add(User(email=EMAIL, password_hash=hash_password(PASSWORD)))
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


def _seed_sport(engine, name: str = "Вейкборд") -> int:
    with Session(engine) as s:
        sport = Sport(name=name, category="action", description="Катание за катером")
        s.add(sport)
        s.commit()
        s.refresh(sport)
        return sport.id


def _seed_achievements(engine, sport_id: int, *specs: tuple[str, str, str]) -> None:
    """specs: (title, level, status)."""
    with Session(engine) as s:
        s.add_all(
            Achievement(user_id=1, sport_id=sport_id, title=t, level=lvl, status=st)
            for t, lvl, st in specs
        )
        s.commit()


def test_list_returns_achievements_for_sport(client, engine):
    sport_id = _seed_sport(engine)
    _seed_achievements(
        engine,
        sport_id,
        ("Старт из воды", "foundation", "locked"),
        ("Прыжок через кильватер", "intermediate", "locked"),
    )

    resp = client.get(f"/sports/{sport_id}/achievements")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert all(a["sport_id"] == sport_id for a in body)
    titles = {a["title"] for a in body}
    assert titles == {"Старт из воды", "Прыжок через кильватер"}


def test_list_serves_statuses(client, engine):
    """Статусы locked/unlocked отдаются как есть."""
    sport_id = _seed_sport(engine)
    _seed_achievements(
        engine,
        sport_id,
        ("Базовый трюк", "foundation", "unlocked"),
        ("Сложный трюк", "advanced", "locked"),
    )

    resp = client.get(f"/sports/{sport_id}/achievements")
    assert resp.status_code == 200
    by_title = {a["title"]: a["status"] for a in resp.json()}
    assert by_title == {"Базовый трюк": "unlocked", "Сложный трюк": "locked"}


def test_list_marks_has_proof(client, engine):
    """has_proof отражает наличие видео-пруфа: с пруфом → true, без → false (S5.6 UI)."""
    sport_id = _seed_sport(engine)
    _seed_achievements(
        engine,
        sport_id,
        ("С пруфом", "foundation", "unlocked"),
        ("Без пруфа", "advanced", "locked"),
    )
    with Session(engine) as s:
        target = s.exec(select(Achievement).where(Achievement.title == "С пруфом")).one()
        s.add(
            AchievementProof(
                achievement_id=target.id,
                video_path="data/videos/x/x.mp4",
                thumbnail_path="data/videos/x/x.jpg",
            )
        )
        s.commit()

    body = client.get(f"/sports/{sport_id}/achievements").json()
    by_title = {a["title"]: a["has_proof"] for a in body}
    assert by_title == {"С пруфом": True, "Без пруфа": False}


def test_list_only_returns_that_sports_achievements(client, engine):
    """Привязка к виду спорта: ачивки другого спорта в выдачу не попадают."""
    wake = _seed_sport(engine, name="Вейкборд")
    bmx = _seed_sport(engine, name="BMX")
    _seed_achievements(engine, wake, ("Рейли", "advanced", "locked"))
    _seed_achievements(engine, bmx, ("Банни-хоп", "foundation", "locked"))

    body = client.get(f"/sports/{bmx}/achievements").json()
    assert len(body) == 1
    assert body[0]["title"] == "Банни-хоп"
    assert body[0]["sport_id"] == bmx


def test_list_empty_for_sport_without_achievements(client, engine):
    sport_id = _seed_sport(engine)
    resp = client.get(f"/sports/{sport_id}/achievements")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_unknown_sport_returns_404(client):
    resp = client.get("/sports/9999/achievements")
    assert resp.status_code == 404
    assert "не найден" in resp.json()["detail"]


def test_list_requires_auth(engine):
    app.dependency_overrides.clear()
    assert TestClient(app).get("/sports/1/achievements").status_code == 401
