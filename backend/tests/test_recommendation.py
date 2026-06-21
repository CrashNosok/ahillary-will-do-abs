"""Генерация рекомендации (S4.4): снапшот → вызов Opus → парс по схеме → запись.

Закрывает критерии карточки:
- «ответ распарсен и сохранён» — успешный вызов пишет `Recommendation` с распарсенным
  планом (`output_json`) по схеме S4.3, моделью и снапшотом-входом;
- «хранится исходный raw для отладки» — `raw_text` хранит сырой текст модели той
  попытки, что прошла валидацию.

Сеть не дёргаем: `llm.text` мокается. Проверяем и сервис напрямую, и HTTP-роуты
под сессией: генерация (POST /generate), список (GET /recommendations) и деталь по id
(GET /recommendations/{id}, S4.5: 200 + 404).
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.config import settings
from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.goal import SmartGoal
from app.models.recommendation import Recommendation
from app.models.user import User
from app.services import llm
from app.services import recommendation as reco_service
from app.services.recommendation_schema import PLAN_EXAMPLE, InvalidPlanError

EMAIL = "reco@example.com"
PASSWORD = "right-password"

VALID_RAW = json.dumps(PLAN_EXAMPLE, ensure_ascii=False)
BAD_RAW = "{ это не валидный JSON"


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


def _seed_goal(engine) -> int:
    with Session(engine) as s:
        goal = SmartGoal(target_weight_kg=75.0, status="active")
        s.add(goal)
        s.commit()
        s.refresh(goal)
        return goal.id


def _reply(*texts: str):
    """Очередь ответов llm.text: на каждый вызов выдаёт следующий текст из списка."""
    queue = list(texts)

    def fake_text(prompt: str, model: str | None = None) -> str:
        return queue.pop(0)

    return fake_text


# --- сервис ------------------------------------------------------------------


def test_generate_persists_parsed_plan_and_raw(engine, monkeypatch):
    """Успех: пишется распарсенный план + сырой текст + модель + снапшот + goal_id."""
    goal_id = _seed_goal(engine)
    monkeypatch.setattr(llm, "text", _reply(VALID_RAW))

    with Session(engine) as session:
        rec = reco_service.generate_recommendation(session)

    assert rec.id is not None
    assert rec.model == settings.model_reco
    assert rec.raw_text == VALID_RAW  # сырой ответ хранится для отладки
    assert rec.goal_id == goal_id  # привязка к активной цели из снапшота
    # Ответ распарсен по схеме S4.3 и сохранён структурой.
    assert rec.output_json["meal_plan"]["training_day"]["calories"] == 2400
    assert rec.output_json["workout_plan"]["days_per_week"] == 3
    assert "sync_note" in rec.output_json
    # S4.9: засечён замер длительности генерации (мс) — целое, не отрицательное.
    assert isinstance(rec.generation_ms, int) and rec.generation_ms >= 0
    # Вход модели сохранён целиком.
    assert set(rec.input_snapshot_json) >= {"goal", "nutrition", "training", "window"}


def test_generate_retries_invalid_then_valid(engine, monkeypatch):
    """Первый ответ отбракован, второй валиден: запись есть, raw — от валидной попытки."""
    monkeypatch.setattr(llm, "text", _reply(BAD_RAW, VALID_RAW))

    with Session(engine) as session:
        rec = reco_service.generate_recommendation(session)
        rows = session.exec(select(Recommendation)).all()

    assert len(rows) == 1
    assert rec.raw_text == VALID_RAW  # raw соответствует сохранённому output_json
    assert rec.output_json["workout_plan"]["days_per_week"] == 3


def test_generate_all_invalid_raises_and_persists_nothing(engine, monkeypatch):
    """Все попытки отбракованы: InvalidPlanError, в БД ничего не записано."""
    monkeypatch.setattr(llm, "text", _reply(BAD_RAW, BAD_RAW, BAD_RAW))

    with Session(engine) as session:
        with pytest.raises(InvalidPlanError):
            reco_service.generate_recommendation(session, attempts=3)
        assert session.exec(select(Recommendation)).all() == []


def test_generate_llm_error_propagates_and_persists_nothing(engine, monkeypatch):
    """Сбой сети/LLM пробрасывается, в БД ничего не записано."""

    def boom(prompt: str, model: str | None = None) -> str:
        raise llm.LLMError("сеть упала")

    monkeypatch.setattr(llm, "text", boom)

    with Session(engine) as session:
        with pytest.raises(llm.LLMError):
            reco_service.generate_recommendation(session)
        assert session.exec(select(Recommendation)).all() == []


def test_build_prompt_carries_snapshot_and_output_schema():
    """Промпт согласован со схемой S4.3: несёт снапшот, схему выхода и пример."""
    snapshot = {"goal": None, "nutrition": {"avg_kcal_in": 1900}, "window": {"days": 90}}
    prompt = reco_service.build_prompt(snapshot)

    assert '"avg_kcal_in": 1900' in prompt  # данные снапшота попали в промпт
    assert "meal_plan" in prompt and "workout_plan" in prompt  # форма выхода = схема S4.3
    assert "Завтрак" in prompt  # пример валидного ответа вшит


# --- роут --------------------------------------------------------------------


def test_post_requires_auth(engine):
    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        assert TestClient(app).post("/recommendations/generate").status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_post_generates_and_get_lists(client, engine, monkeypatch):
    """POST /generate генерирует и сохраняет (201), GET возвращает её в списке."""
    monkeypatch.setattr(llm, "text", _reply(VALID_RAW))

    resp = client.post("/recommendations/generate")
    assert resp.status_code == 201
    body = resp.json()
    assert body["model"] == settings.model_reco
    assert body["raw_text"] == VALID_RAW
    assert body["output_json"]["workout_plan"]["days_per_week"] == 3
    assert isinstance(body["generation_ms"], int) and body["generation_ms"] >= 0  # S4.9

    listed = client.get("/recommendations")
    assert listed.status_code == 200
    items = listed.json()
    assert len(items) == 1
    assert items[0]["id"] == body["id"]


def test_get_detail_returns_full_record(client, monkeypatch):
    """GET /{id} (S4.5): деталь по id отдаёт сохранённую запись целиком."""
    monkeypatch.setattr(llm, "text", _reply(VALID_RAW))
    created = client.post("/recommendations/generate").json()

    resp = client.get(f"/recommendations/{created['id']}")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["id"] == created["id"]
    assert detail["raw_text"] == VALID_RAW
    # Деталь несёт распарсенный план и вход модели — это и есть «просмотр прошлой».
    assert detail["output_json"]["meal_plan"]["training_day"]["calories"] == 2400
    assert set(detail["input_snapshot_json"]) >= {"goal", "nutrition", "training", "window"}


def test_get_detail_unknown_id_returns_404(client):
    """GET /{id} (S4.5): несуществующий id → 404 с понятным сообщением."""
    resp = client.get("/recommendations/9999")
    assert resp.status_code == 404
    assert "не найдена" in resp.json()["detail"]


def test_get_detail_requires_auth(engine):
    """Деталь под сессией: без логина → 401."""

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        assert TestClient(app).get("/recommendations/1").status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_post_llm_error_returns_502(client, monkeypatch):
    """Сбой модели → 502, тело с понятным сообщением."""

    def boom(prompt: str, model: str | None = None) -> str:
        raise llm.LLMError("апстрим недоступен")

    monkeypatch.setattr(llm, "text", boom)

    resp = client.post("/recommendations/generate")
    assert resp.status_code == 502
    assert "модели" in resp.json()["detail"]
