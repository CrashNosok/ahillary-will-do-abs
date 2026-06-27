"""Челленджи (M6·B34): POST/GET /challenges + POST /challenges/{id}/join.

Залогинен user(id=1). Проверяем: создание челленджа (creator_user_id берётся из
сессии, а не из тела), 404 на несуществующий sport, обязательность полей (422),
список всех челленджей по заголовку, участие через join (201, participant с
user_id=1, статус active), 404 на join несуществующего, 409 на повторный join,
и 401 без сессии.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401 — регистрирует все таблицы в SQLModel.metadata
from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.sport import Sport
from app.models.user import User

EMAIL = "challenger@example.com"
PASSWORD = "right-password"


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def client(engine):
    with Session(engine) as session:
        session.add(User(email=EMAIL, password_hash=hash_password(PASSWORD)))  # id=1
        session.commit()

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    test_client = TestClient(app)
    test_client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    yield test_client
    app.dependency_overrides.clear()


def _make_sport(engine, name: str, category: str = "strength") -> int:
    with Session(engine) as session:
        sport = Sport(name=name, category=category)
        session.add(sport)
        session.commit()
        session.refresh(sport)
        return sport.id


def test_create_challenge_returns_201_with_creator_from_session(client, engine):
    sid = _make_sport(engine, "Калистеника")
    resp = client.post(
        "/challenges",
        json={"sport_id": sid, "title": "100 отжиманий", "description": "за один подход"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] is not None
    assert body["sport_id"] == sid
    assert body["title"] == "100 отжиманий"
    assert body["description"] == "за один подход"
    assert body["creator_user_id"] == 1  # из сессии
    assert body["is_base"] is False  # пользовательский по умолчанию


def test_create_challenge_ignores_creator_in_body(client, engine):
    """creator_user_id берётся из сессии, тело его не переопределяет."""
    sid = _make_sport(engine, "Бег")
    body = client.post(
        "/challenges",
        json={
            "sport_id": sid,
            "title": "Марафон",
            "description": "42км",
            "creator_user_id": 999,
        },
    ).json()
    assert body["creator_user_id"] == 1  # игнор подменённого автора


def test_create_challenge_unknown_sport_returns_404(client):
    resp = client.post(
        "/challenges",
        json={"sport_id": 999, "title": "x", "description": "y"},
    )
    assert resp.status_code == 404


def test_create_challenge_requires_fields(client, engine):
    sid = _make_sport(engine, "Плавание")
    assert client.post("/challenges", json={"sport_id": sid, "title": "x"}).status_code == 422
    assert client.post("/challenges", json={"title": "x", "description": "y"}).status_code == 422


def test_list_challenges_returns_all_sorted_by_title(client, engine):
    sid = _make_sport(engine, "Бокс")
    client.post("/challenges", json={"sport_id": sid, "title": "Яблоко", "description": "d"})
    client.post("/challenges", json={"sport_id": sid, "title": "Арбуз", "description": "d"})
    resp = client.get("/challenges")
    assert resp.status_code == 200
    titles = [c["title"] for c in resp.json()]
    assert titles == ["Арбуз", "Яблоко"]  # по заголовку


def test_join_challenge_returns_201_with_participant(client, engine):
    sid = _make_sport(engine, "Йога")
    cid = client.post(
        "/challenges", json={"sport_id": sid, "title": "30 дней", "description": "d"}
    ).json()["id"]
    resp = client.post(f"/challenges/{cid}/join")
    assert resp.status_code == 201
    body = resp.json()
    assert body["challenge_id"] == cid
    assert body["user_id"] == 1  # участник = текущий пользователь
    assert body["status"] == "active"


def test_join_unknown_challenge_returns_404(client):
    assert client.post("/challenges/999/join").status_code == 404


def test_join_twice_returns_409(client, engine):
    sid = _make_sport(engine, "Скейт", "action")
    cid = client.post(
        "/challenges", json={"sport_id": sid, "title": "Олли", "description": "d"}
    ).json()["id"]
    assert client.post(f"/challenges/{cid}/join").status_code == 201
    assert client.post(f"/challenges/{cid}/join").status_code == 409  # повторный join


def test_my_participations_empty_then_reflects_join(client, engine):
    """GET /challenges/participations: пусто до join, после — моё участие со статусом."""
    sid = _make_sport(engine, "Сёрф", "action")
    cid = client.post(
        "/challenges", json={"sport_id": sid, "title": "Первая волна", "description": "d"}
    ).json()["id"]
    assert client.get("/challenges/participations").json() == []
    client.post(f"/challenges/{cid}/join")
    parts = client.get("/challenges/participations").json()
    assert [(p["challenge_id"], p["status"]) for p in parts] == [(cid, "active")]


def test_my_participations_excludes_other_user(client, engine):
    """Участие чужого юзера (id=2) не попадает в мои участия (скоуп по user_id)."""
    from app.models.challenge import ChallengeParticipant

    sid = _make_sport(engine, "Вейк", "action")
    cid = client.post(
        "/challenges", json={"sport_id": sid, "title": "Бэксайд", "description": "d"}
    ).json()["id"]
    with Session(engine) as session:
        session.add(User(email="other@example.com", password_hash=hash_password("x")))  # id=2
        session.commit()
        session.add(ChallengeParticipant(challenge_id=cid, user_id=2))
        session.commit()
    assert client.get("/challenges/participations").json() == []  # чужое участие не видно


def test_challenges_require_auth():
    app.dependency_overrides.clear()
    unauth = TestClient(app)
    assert unauth.get("/challenges").status_code == 401
    assert unauth.get("/challenges/participations").status_code == 401
    create = unauth.post("/challenges", json={"sport_id": 1, "title": "x", "description": "y"})
    assert create.status_code == 401
    assert unauth.post("/challenges/1/join").status_code == 401
