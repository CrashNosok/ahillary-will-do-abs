"""ИИ-рекомендация по виду спорта (#1): GET (последняя/null) + POST (генерация, upsert).

Сеть не дёргаем: llm.text замокан. Закрываем: пусто → null; генерация пишет совет и GET его
отдаёт; повтор обновляет ту же строку (upsert, без дублей); ошибка модели → 502 (ничего не
пишем); неизвестный вид → 404; роуты под сессией.
"""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401 — регистрирует таблицы
from app.api import sports
from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.sport import Sport
from app.models.sport_advice import SportAdvice
from app.models.user import User
from app.services import sport_advice as advice_service
from app.services.llm import LLMError

EMAIL = "advice@example.com"
PASSWORD = "right-password"


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(User(email=EMAIL, password_hash=hash_password(PASSWORD)))
        s.add(Sport(name="Вейкборд", category="action"))
        s.commit()
    return eng


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    monkeypatch.setattr(advice_service.llm, "text", lambda prompt, model=None: "## Навыки\n- рейли")


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


def _sport_id(engine) -> int:
    with Session(engine) as s:
        return s.exec(select(Sport.id)).first()


def test_get_null_then_generate_then_get(client, engine):
    sid = _sport_id(engine)
    assert client.get(f"/sports/{sid}/recommendation").json() is None
    gen = client.post(f"/sports/{sid}/recommendation")
    assert gen.status_code == 201
    assert "рейли" in gen.json()["text"]
    assert client.get(f"/sports/{sid}/recommendation").json()["text"] == gen.json()["text"]


def test_generate_upserts_single_row(client, engine, monkeypatch):
    # Кулдаун обнуляем, чтобы второй вызов реально дошёл до upsert (а не отбился 429).
    monkeypatch.setattr(sports, "_ADVICE_COOLDOWN", dt.timedelta(0))
    sid = _sport_id(engine)
    assert client.post(f"/sports/{sid}/recommendation").status_code == 201
    assert client.post(f"/sports/{sid}/recommendation").status_code == 201
    with Session(engine) as s:
        assert len(s.exec(select(SportAdvice)).all()) == 1  # upsert, не дубль


def test_second_generate_within_cooldown_returns_429(client, engine):
    sid = _sport_id(engine)
    assert client.post(f"/sports/{sid}/recommendation").status_code == 201
    resp = client.post(f"/sports/{sid}/recommendation")  # сразу повтор — упирается в кулдаун
    assert resp.status_code == 429
    assert resp.headers.get("Retry-After")  # подсказка, через сколько можно


def test_unknown_sport_returns_404(client):
    assert client.get("/sports/999/recommendation").status_code == 404
    assert client.post("/sports/999/recommendation").status_code == 404


def test_model_error_returns_502_and_writes_nothing(client, engine, monkeypatch):
    def boom(prompt, model=None):
        raise LLMError("down")

    monkeypatch.setattr(advice_service.llm, "text", boom)
    sid = _sport_id(engine)
    assert client.post(f"/sports/{sid}/recommendation").status_code == 502
    with Session(engine) as s:
        assert s.exec(select(SportAdvice)).all() == []


def test_requires_auth(engine):
    app.dependency_overrides.clear()
    assert TestClient(app).get("/sports/1/recommendation").status_code == 401
