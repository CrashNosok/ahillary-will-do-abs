"""M2·B19 — /me/sports: список дисциплин пользователя + link/unlink.

Залогинен user(id=1). Проверяем: привязка дисциплины (201, с rating/level), список
со связкой и полями каталога, 404 на несуществующий спорт, 409 на повторный link,
отвязка (204) и 404 на отвязку непривязанной. Скоуп по владельцу: чужая связка
user(id=2) не видна в списке и не отвязывается (404, а не 403 — чтобы не раскрывать).
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
from app.models.user_sport import UserSport

EMAIL = "athlete@example.com"
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


def test_link_sport_returns_201_with_catalog_fields(client, engine):
    sid = _make_sport(engine, "Калистеника", "strength")
    resp = client.post("/me/sports", json={"sport_id": sid, "current_level_id": 3, "rating": 4.5})
    assert resp.status_code == 201
    body = resp.json()
    assert body["sport_id"] == sid
    assert body["name"] == "Калистеника"
    assert body["category"] == "strength"
    assert body["current_level_id"] == 3
    assert body["rating"] == 4.5
    assert body["joined_at"] is not None


def test_link_optional_fields_default_to_null(client, engine):
    sid = _make_sport(engine, "Бег", "endurance")
    body = client.post("/me/sports", json={"sport_id": sid}).json()
    assert body["current_level_id"] is None
    assert body["rating"] is None


def test_linked_sport_appears_in_list(client, engine):
    sid = _make_sport(engine, "Плавание", "endurance")
    client.post("/me/sports", json={"sport_id": sid})
    resp = client.get("/me/sports")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["sport_id"] == sid
    assert rows[0]["name"] == "Плавание"


def test_list_orders_by_sport_name(client, engine):
    for name in ("Яхтинг", "Альпинизм", "Бокс"):
        sid = _make_sport(engine, name, "other")
        client.post("/me/sports", json={"sport_id": sid})
    names = [r["name"] for r in client.get("/me/sports").json()]
    assert names == ["Альпинизм", "Бокс", "Яхтинг"]


def test_link_unknown_sport_returns_404(client):
    assert client.post("/me/sports", json={"sport_id": 999}).status_code == 404


def test_duplicate_link_returns_409(client, engine):
    sid = _make_sport(engine, "Жим", "strength")
    assert client.post("/me/sports", json={"sport_id": sid}).status_code == 201
    assert client.post("/me/sports", json={"sport_id": sid}).status_code == 409


def test_unlink_removes_from_list(client, engine):
    sid = _make_sport(engine, "Йога", "artistic")
    client.post("/me/sports", json={"sport_id": sid})
    assert client.delete(f"/me/sports/{sid}").status_code == 204
    assert client.get("/me/sports").json() == []


def test_relink_after_unlink_restores_level(client, engine):
    # Мягкая отвязка: уровень сохраняется и восстанавливается при повторной привязке без него.
    sid = _make_sport(engine, "Сноуборд", "action")
    client.post("/me/sports", json={"sport_id": sid, "current_level_id": 3})
    client.delete(f"/me/sports/{sid}")  # отвязали — из активных ушёл, но строка осталась
    assert client.get("/me/sports").json() == []
    resp = client.post("/me/sports", json={"sport_id": sid})  # повторно, без уровня
    assert resp.status_code == 201
    assert resp.json()["current_level_id"] == 3  # прежний уровень сохранён
    assert len(client.get("/me/sports").json()) == 1


def test_unlink_not_linked_returns_404(client, engine):
    sid = _make_sport(engine, "Бокс", "combat")
    assert client.delete(f"/me/sports/{sid}").status_code == 404  # спорт есть, связки нет


def test_list_excludes_other_users_links(client, engine):
    """Связка чужого user(id=2) не попадает в /me/sports владельца (скоуп по user_id)."""
    sid = _make_sport(engine, "Сёрфинг", "action")
    with Session(engine) as session:
        session.add(User(email="other@example.com", password_hash=hash_password(PASSWORD)))  # id=2
        session.commit()
        session.add(UserSport(user_id=2, sport_id=sid))
        session.commit()
    assert client.get("/me/sports").json() == []  # своих связок нет


def test_unlink_other_users_link_returns_404(client, engine):
    """Нельзя отвязать чужую связку — 404 (не раскрываем факт её существования)."""
    sid = _make_sport(engine, "Скейт", "action")
    with Session(engine) as session:
        session.add(User(email="other2@example.com", password_hash=hash_password(PASSWORD)))  # id=2
        session.commit()
        session.add(UserSport(user_id=2, sport_id=sid))
        session.commit()
    assert client.delete(f"/me/sports/{sid}").status_code == 404
    with Session(engine) as session:  # чужая связка цела
        assert session.get(UserSport, (2, sid)) is not None


def test_me_sports_require_auth():
    app.dependency_overrides.clear()
    unauth = TestClient(app)
    assert unauth.get("/me/sports").status_code == 401
    assert unauth.post("/me/sports", json={"sport_id": 1}).status_code == 401
    assert unauth.delete("/me/sports/1").status_code == 401
