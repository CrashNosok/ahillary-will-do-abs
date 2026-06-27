"""План навыков через достижения: plan (locked→in_progress) / unplan (in_progress→locked).

Закрывает: plan переводит locked→in_progress без пруфа; unplan возвращает in_progress→locked;
unlocked (терминал) не трогается ни тем, ни другим; чужая/неизвестная ачивка → 404; роуты под
сессией. Закрытие (unlocked) остаётся пруф-гейтом (см. test_achievement_unlock).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401 — регистрирует таблицы
from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.achievement import Achievement
from app.models.user import User

EMAIL = "plan@example.com"
PASSWORD = "right-password"


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(User(email=EMAIL, password_hash=hash_password(PASSWORD)))  # id=1
        s.add(User(email="other@example.com", password_hash=hash_password("x")))  # id=2
        s.add(Achievement(id=1, user_id=1, sport_id=None, title="Рейли", status="locked"))
        s.add(Achievement(id=2, user_id=1, sport_id=None, title="Грэб", status="in_progress"))
        s.add(Achievement(id=3, user_id=1, sport_id=None, title="180", status="unlocked"))
        s.add(Achievement(id=4, user_id=2, sport_id=None, title="Чужой", status="locked"))
        s.commit()
    return eng


@pytest.fixture
def client(engine):
    def override():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = override
    c = TestClient(app)
    c.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    yield c
    app.dependency_overrides.clear()


def _status(engine, aid: int) -> str:
    with Session(engine) as s:
        return s.get(Achievement, aid).status


def test_plan_locked_to_in_progress(client, engine):
    assert client.post("/achievements/1/plan").json()["status"] == "in_progress"
    assert _status(engine, 1) == "in_progress"


def test_unplan_in_progress_to_locked(client, engine):
    assert client.post("/achievements/2/unplan").json()["status"] == "locked"
    assert _status(engine, 2) == "locked"


def test_plan_and_unplan_never_touch_unlocked(client, engine):
    assert client.post("/achievements/3/plan").json()["status"] == "unlocked"
    assert client.post("/achievements/3/unplan").json()["status"] == "unlocked"
    assert _status(engine, 3) == "unlocked"


def test_plan_other_users_achievement_returns_404(client, engine):
    assert client.post("/achievements/4/plan").status_code == 404
    assert _status(engine, 4) == "locked"  # чужая не тронута


def test_plan_unknown_returns_404(client):
    assert client.post("/achievements/999/plan").status_code == 404


def test_requires_auth():
    app.dependency_overrides.clear()
    unauth = TestClient(app)
    assert unauth.post("/achievements/1/plan").status_code == 401
