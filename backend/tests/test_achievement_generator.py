"""Генератор ачивок (S5.1): дисциплина+уровень → вызов Opus → парс по схеме → запись.

Закрывает критерии карточки на уровне сервиса и HTTP-роута:
- успешная генерация пишет строки `Achievement` (FK sport_id), тир хранится в `level`;
- набор тирован по сложности и безопасен под уровень (валидируется схемой S5.1);
- новичку (default level) опасные элементы не попадают;
- ошибка модели → 502, в БД при этом ничего не пишется.

Сеть не дёргаем: `llm.text` мокается.
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.achievement import Achievement
from app.models.sport import Sport
from app.models.user import User
from app.services import achievement as achievement_service
from app.services import llm
from app.services.achievement_schema import (
    ACHIEVEMENT_SET_EXAMPLE,
    AthleteLevel,
    InvalidAchievementSetError,
)

EMAIL = "ach@example.com"
PASSWORD = "right-password"

VALID_RAW = json.dumps(ACHIEVEMENT_SET_EXAMPLE, ensure_ascii=False)
BAD_RAW = "{ это не валидный JSON"


def _advanced_raw() -> str:
    """Валидный набор уровня advanced с elite-тиром и опасным трюком."""
    data = json.loads(VALID_RAW)
    data["level"] = "advanced"
    data["achievements"][-1]["tier"] = "elite"
    data["achievements"][-1]["is_dangerous"] = True
    return json.dumps(data, ensure_ascii=False)


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
        sport = Sport(name=name, type="skill", description="Катание за катером")
        s.add(sport)
        s.commit()
        s.refresh(sport)
        return sport.id


def _reply(*texts: str):
    """Очередь ответов llm.text: на каждый вызов выдаёт следующий текст из списка."""
    queue = list(texts)

    def fake_text(prompt: str, model: str | None = None) -> str:
        return queue.pop(0)

    return fake_text


# --- сервис ------------------------------------------------------------------


def test_generate_persists_tiered_achievements(engine, monkeypatch):
    """Успех: пишутся строки Achievement c тиром в поле level, привязка к спорту."""
    sport_id = _seed_sport(engine)
    monkeypatch.setattr(llm, "text", _reply(VALID_RAW))

    with Session(engine) as session:
        sport = session.get(Sport, sport_id)
        created = achievement_service.generate_achievements(session, sport, AthleteLevel.beginner)

    assert len(created) == len(ACHIEVEMENT_SET_EXAMPLE["achievements"])
    assert all(a.sport_id == sport_id for a in created)
    assert all(a.status == "locked" for a in created)
    # Тируется по сложности: в поле level лежат >= 2 разных тира.
    assert len({a.level for a in created}) >= 2
    # Новичку — без опасного: эталон beginner состоит из безопасных тиров (не выше intermediate).
    assert {a.level for a in created} <= {"foundation", "intermediate"}


def test_generate_beginner_has_no_advanced_tier(engine, monkeypatch):
    """Новичку модель не «протолкнёт» опасный набор: ответ с advanced-тиром отбраковывается."""
    sport_id = _seed_sport(engine)
    # Модель «ошибается» (advanced-тир для beginner), потом исправляется до валидного.
    bad = json.loads(VALID_RAW)
    bad["achievements"][-1]["tier"] = "advanced"
    monkeypatch.setattr(llm, "text", _reply(json.dumps(bad, ensure_ascii=False), VALID_RAW))

    with Session(engine) as session:
        sport = session.get(Sport, sport_id)
        created = achievement_service.generate_achievements(session, sport, AthleteLevel.beginner)

    assert all(a.level in {"foundation", "intermediate"} for a in created)


def test_generate_retries_invalid_then_valid(engine, monkeypatch):
    """Первый ответ отбракован, второй валиден: записан ровно один набор."""
    sport_id = _seed_sport(engine)
    monkeypatch.setattr(llm, "text", _reply(BAD_RAW, VALID_RAW))

    with Session(engine) as session:
        sport = session.get(Sport, sport_id)
        achievement_service.generate_achievements(session, sport, AthleteLevel.beginner)
        rows = session.exec(select(Achievement)).all()

    assert len(rows) == len(ACHIEVEMENT_SET_EXAMPLE["achievements"])


def test_generate_all_invalid_persists_nothing(engine, monkeypatch):
    """Все попытки отбракованы: InvalidAchievementSetError, в БД ничего не записано."""
    sport_id = _seed_sport(engine)
    monkeypatch.setattr(llm, "text", _reply(BAD_RAW, BAD_RAW, BAD_RAW))

    with Session(engine) as session:
        sport = session.get(Sport, sport_id)
        with pytest.raises(InvalidAchievementSetError):
            achievement_service.generate_achievements(
                session, sport, AthleteLevel.beginner, attempts=3
            )
        assert session.exec(select(Achievement)).all() == []


def test_generate_llm_error_propagates_and_persists_nothing(engine, monkeypatch):
    """Сбой сети/LLM пробрасывается, в БД ничего не записано."""

    def boom(prompt: str, model: str | None = None) -> str:
        raise llm.LLMError("сеть упала")

    sport_id = _seed_sport(engine)
    monkeypatch.setattr(llm, "text", boom)

    with Session(engine) as session:
        sport = session.get(Sport, sport_id)
        with pytest.raises(llm.LLMError):
            achievement_service.generate_achievements(session, sport, AthleteLevel.beginner)
        assert session.exec(select(Achievement)).all() == []


def test_build_prompt_carries_sport_level_and_schema(engine):
    """Промпт несёт дисциплину, уровень и схему выхода (форма запроса = форма парсинга)."""
    sport_id = _seed_sport(engine, name="BMX")
    with Session(engine) as session:
        sport = session.get(Sport, sport_id)
        prompt = achievement_service.build_prompt(sport, AthleteLevel.beginner)

    assert "BMX" in prompt  # дисциплина попала в промпт
    assert "beginner" in prompt  # уровень атлета передан
    assert "is_dangerous" in prompt and "tier" in prompt  # форма выхода = схема S5.1
    assert "Вейкборд" in prompt  # пример валидного ответа вшит


# --- роут --------------------------------------------------------------------


def test_post_requires_auth(engine):
    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        resp = TestClient(app).post("/sports/1/achievements/generate")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_post_generates_beginner_by_default(client, engine, monkeypatch):
    """POST без level генерирует безопасный набор новичка (201), тир в поле level."""
    sport_id = _seed_sport(engine)
    monkeypatch.setattr(llm, "text", _reply(VALID_RAW))

    resp = client.post(f"/sports/{sport_id}/achievements/generate")
    assert resp.status_code == 201
    body = resp.json()
    assert len(body) == len(ACHIEVEMENT_SET_EXAMPLE["achievements"])
    assert all(a["sport_id"] == sport_id for a in body)
    assert len({a["level"] for a in body}) >= 2  # тируется по сложности
    assert {a["level"] for a in body} <= {"foundation", "intermediate"}  # без опасного


def test_post_respects_level_query(client, engine, monkeypatch):
    """level=advanced пропускает elite-тир и опасный трюк (это валидно для продвинутого)."""
    sport_id = _seed_sport(engine)
    monkeypatch.setattr(llm, "text", _reply(_advanced_raw()))

    resp = client.post(f"/sports/{sport_id}/achievements/generate?level=advanced")
    assert resp.status_code == 201
    levels = {a["level"] for a in resp.json()}
    assert "elite" in levels


def test_post_unknown_sport_returns_404(client):
    """Неизвестный sport_id → 404 (LLM не дёргается)."""
    resp = client.post("/sports/9999/achievements/generate")
    assert resp.status_code == 404
    assert "не найден" in resp.json()["detail"]


def test_post_llm_error_returns_502(client, engine, monkeypatch):
    """Сбой модели → 502 с понятным сообщением, в БД ничего не записано."""
    sport_id = _seed_sport(engine)

    def boom(prompt: str, model: str | None = None) -> str:
        raise llm.LLMError("апстрим недоступен")

    monkeypatch.setattr(llm, "text", boom)

    resp = client.post(f"/sports/{sport_id}/achievements/generate")
    assert resp.status_code == 502
    assert "модели" in resp.json()["detail"]

    with Session(engine) as session:
        assert session.exec(select(Achievement)).all() == []
