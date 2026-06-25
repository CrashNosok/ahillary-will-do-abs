"""Список-эндпоинты секций дисциплины (M5·B28): /sports/{id}/levels|events|mentors|recommendations.

Каждая секция каталога дисциплины (ступени, события, менторы, рекомендации) доступна
отдельным GET-эндпоинтом с тем же порядком, что и в сводке /overview (B27): уровни по rank,
события по дате старта, менторы по имени, рекомендации по id. Каталог глобален (без user-скоупа).
404 для неизвестной дисциплины, 401 без сессии, пустой список для дисциплины без записей.
"""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.sport import (
    SportEvent,
    SportLevel,
    SportMentor,
    SportRecommendation,
)
from app.models.user import User

EMAIL = "sections@example.com"
PASSWORD = "right-password"


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(email=EMAIL, password_hash=hash_password(PASSWORD)))  # id == 1
        session.commit()

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    test_client = TestClient(app)
    test_client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    test_client._engine = engine  # ручка для прямого посева каталога
    yield test_client
    app.dependency_overrides.clear()


def _seed_sport(client) -> int:
    return client.post("/sports", json={"name": "Бег", "category": "endurance"}).json()["id"]


def _seed_catalog(engine, sport_id: int) -> None:
    """2 уровня (rank вразнобой), 2 события (даты вразнобой), 2 ментора (имена вразнобой), 1 рек."""
    with Session(engine) as s:
        s.add(SportLevel(sport_id=sport_id, code="amateur", label="Любитель", rank=2))
        s.add(SportLevel(sport_id=sport_id, code="beginner", label="Новичок", rank=1))
        s.add(SportEvent(sport_id=sport_id, title="Осенний марафон", starts_on=dt.date(2026, 9, 1)))
        s.add(SportEvent(sport_id=sport_id, title="Весенний забег", starts_on=dt.date(2026, 4, 1)))
        s.add(SportMentor(sport_id=sport_id, name="Тренер Б"))
        s.add(SportMentor(sport_id=sport_id, name="Тренер А"))
        s.add(SportRecommendation(sport_id=sport_id, title="Совет", body="Бегайте регулярно."))
        s.commit()


def test_levels_ordered_by_rank(client):
    sport_id = _seed_sport(client)
    _seed_catalog(client._engine, sport_id)
    resp = client.get(f"/sports/{sport_id}/levels")
    assert resp.status_code == 200
    assert [lvl["rank"] for lvl in resp.json()] == [1, 2]  # по возрастанию rank


def test_events_ordered_by_start_date(client):
    sport_id = _seed_sport(client)
    _seed_catalog(client._engine, sport_id)
    resp = client.get(f"/sports/{sport_id}/events")
    assert resp.status_code == 200
    assert [ev["starts_on"] for ev in resp.json()] == ["2026-04-01", "2026-09-01"]


def test_mentors_ordered_by_name(client):
    sport_id = _seed_sport(client)
    _seed_catalog(client._engine, sport_id)
    resp = client.get(f"/sports/{sport_id}/mentors")
    assert resp.status_code == 200
    assert [m["name"] for m in resp.json()] == ["Тренер А", "Тренер Б"]


def test_recommendations_listed(client):
    sport_id = _seed_sport(client)
    _seed_catalog(client._engine, sport_id)
    resp = client.get(f"/sports/{sport_id}/recommendations")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["title"] == "Совет"


@pytest.mark.parametrize("section", ["levels", "events", "mentors", "recommendations"])
def test_empty_sport_returns_empty_list(client, section):
    sport_id = _seed_sport(client)  # каталог не наполняем
    resp = client.get(f"/sports/{sport_id}/{section}")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.parametrize("section", ["levels", "events", "mentors", "recommendations"])
def test_unknown_sport_returns_404(client, section):
    resp = client.get(f"/sports/9999/{section}")
    assert resp.status_code == 404


@pytest.mark.parametrize("section", ["levels", "events", "mentors", "recommendations"])
def test_requires_auth(client, section):
    client.cookies.clear()  # без сессии — guard CurrentUser отдаёт 401
    resp = client.get(f"/sports/1/{section}")
    assert resp.status_code == 401
