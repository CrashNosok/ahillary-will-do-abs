"""Сводка по виду спорта (M5·B27): sport_overview() + GET /sports/{id}/overview.

Закрывает критерии карточки: DTO агрегирует уровни + события + менторы +
рекомендации + счётчик ачивок. Каталожные таблицы глобальны (отдаём как есть,
упорядоченно); achievement_count скоупится по владельцу (чужие ачивки не в счёте).
404 для неизвестной дисциплины.
"""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.achievement import Achievement
from app.models.sport import (
    SportEvent,
    SportLevel,
    SportMentor,
    SportRecommendation,
)
from app.models.user import User

EMAIL = "overview@example.com"
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
        # второй пользователь (id == 2) — для проверки скоупа счётчика ачивок
        session.add(User(email="other@example.com", password_hash=hash_password(PASSWORD)))
        session.commit()

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    test_client = TestClient(app)
    test_client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    test_client._engine = engine  # ручка для прямого посева каталога/ачивок в тестах
    yield test_client
    app.dependency_overrides.clear()


def _seed_sport(client) -> int:
    """Создаёт дисциплину через API и возвращает её id."""
    return client.post("/sports", json={"name": "Бег", "category": "endurance"}).json()["id"]


def _seed_catalog(engine, sport_id: int) -> None:
    """Наполняет глобальный каталог дисциплины: 2 уровня, 2 события, 2 ментора, 1 рекомендация."""
    with Session(engine) as s:
        s.add(SportLevel(sport_id=sport_id, code="amateur", label="Любитель", rank=2))
        s.add(SportLevel(sport_id=sport_id, code="beginner", label="Новичок", rank=1))
        s.add(SportEvent(sport_id=sport_id, title="Осенний марафон", starts_on=dt.date(2026, 9, 1)))
        s.add(SportEvent(sport_id=sport_id, title="Весенний забег", starts_on=dt.date(2026, 4, 1)))
        s.add(SportMentor(sport_id=sport_id, name="Тренер Б"))
        s.add(SportMentor(sport_id=sport_id, name="Тренер А"))
        s.add(SportRecommendation(sport_id=sport_id, title="Совет", body="Бегайте регулярно."))
        s.commit()


def test_overview_bundles_catalog_and_counts(client):
    sport_id = _seed_sport(client)
    _seed_catalog(client._engine, sport_id)
    # Две ачивки владельца (id=1) + одна чужая (id=2) — чужая в счётчик не попадает.
    with Session(client._engine) as s:
        s.add(Achievement(user_id=1, sport_id=sport_id, title="A1"))
        s.add(Achievement(user_id=1, sport_id=sport_id, title="A2"))
        s.add(Achievement(user_id=2, sport_id=sport_id, title="Чужая"))
        s.commit()

    resp = client.get(f"/sports/{sport_id}/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sport"]["id"] == sport_id
    assert body["sport"]["name"] == "Бег"
    assert len(body["levels"]) == 2
    assert len(body["events"]) == 2
    assert len(body["mentors"]) == 2
    assert len(body["recommendations"]) == 1
    assert body["achievement_count"] == 2  # только ачивки владельца


def test_overview_orders_levels_by_rank_and_events_by_date(client):
    sport_id = _seed_sport(client)
    _seed_catalog(client._engine, sport_id)
    body = client.get(f"/sports/{sport_id}/overview").json()
    assert [lvl["rank"] for lvl in body["levels"]] == [1, 2]  # по возрастанию rank
    assert [ev["starts_on"] for ev in body["events"]] == ["2026-04-01", "2026-09-01"]  # по дате


def test_overview_empty_sport_returns_empty_lists_and_zero(client):
    sport_id = _seed_sport(client)  # каталог не наполняем
    body = client.get(f"/sports/{sport_id}/overview").json()
    assert body["levels"] == []
    assert body["events"] == []
    assert body["mentors"] == []
    assert body["recommendations"] == []
    assert body["achievement_count"] == 0


def test_overview_returns_saved_level_even_when_unlinked(client):
    """current_level_id отдаётся даже у ОТВЯЗАННОГО вида (мягкая отвязка не теряет уровень)."""
    from sqlmodel import select

    from app.models.sport import SportLevel
    from app.models.user_sport import UserSport

    sport_id = _seed_sport(client)
    _seed_catalog(client._engine, sport_id)
    with Session(client._engine) as s:
        level_id = s.exec(select(SportLevel.id).where(SportLevel.sport_id == sport_id)).first()
        # Связка отвязана (linked=False), но сохранённый уровень остаётся на строке.
        s.add(UserSport(user_id=1, sport_id=sport_id, current_level_id=level_id, linked=False))
        s.commit()
    body = client.get(f"/sports/{sport_id}/overview").json()
    assert body["current_level_id"] == level_id


def test_overview_unknown_sport_returns_404(client):
    resp = client.get("/sports/9999/overview")
    assert resp.status_code == 404


def test_overview_requires_auth(client):
    client.cookies.clear()  # без сессии — guard CurrentUser отдаёт 401
    resp = client.get("/sports/1/overview")
    assert resp.status_code == 401
