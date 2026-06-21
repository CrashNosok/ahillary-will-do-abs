"""Эндпоинты импорта еды (S1.8): превью + сохранение + идемпотентность по дню.

Закрывает критерии карточки:
- загрузка сэмпла создаёт записи дня (POST /import/food);
- повторная загрузка того же дня не дублирует записи (replace_day).
Плюс: превью не пишет в БД, мусорный CSV → 422, роуты под авторизацией.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401 — регистрирует таблицы в SQLModel.metadata
from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models import FoodEntry
from app.models.user import User

EMAIL = "import@example.com"
PASSWORD = "right-password"
_SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "FoodDiary_260620_foods.csv"


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
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
    test_client = TestClient(app)
    test_client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    yield test_client
    app.dependency_overrides.clear()


def _upload(
    client: TestClient,
    path: str,
    content: bytes | None = None,
    filename: str | None = None,
):
    raw = content if content is not None else _SAMPLE.read_bytes()
    return client.post(path, files={"file": (filename or _SAMPLE.name, raw, "text/csv")})


def _rows(engine) -> list[FoodEntry]:
    with Session(engine) as session:
        return session.exec(select(FoodEntry)).all()


def test_preview_returns_parsed_day_without_saving(client, engine):
    resp = _upload(client, "/import/food/preview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["date"] == "2026-06-20"
    assert body["product_count"] == 7
    assert body["saved"] is False
    assert body["import_id"] is None
    # приёмы разнесены, итоги дня посчитаны
    assert [m["meal"] for m in body["meals"]] == ["Завтрак", "Обед", "Ужин"]
    assert body["totals"]["kcal"] == 3250.0
    assert body["totals"]["protein_g"] == 138.45
    assert body["meals"][0]["totals"]["kcal"] == 455.0
    # превью НЕ пишет в БД
    assert _rows(engine) == []


def test_import_creates_day_records(client, engine):
    # критерий приёмки: загрузка сэмпла создаёт записи дня
    resp = _upload(client, "/import/food")
    assert resp.status_code == 201
    body = resp.json()
    assert body["saved"] is True
    assert body["import_id"]
    rows = _rows(engine)
    assert len(rows) == 7
    assert all(str(r.date) == "2026-06-20" for r in rows)
    assert len({r.import_id for r in rows}) == 1


def test_reimport_same_day_does_not_duplicate(client, engine):
    # критерий приёмки: повторная загрузка не дублирует день
    _upload(client, "/import/food")
    second = _upload(client, "/import/food")
    assert second.status_code == 201
    rows = _rows(engine)
    assert len(rows) == 7  # заменены, не добавлены
    # новый импорт — новый import_id (старые записи удалены)
    assert len({r.import_id for r in rows}) == 1


def test_garbage_csv_returns_422(client, engine):
    # дата не извлечётся ни из текста, ни из имени файла → 422
    resp = _upload(client, "/import/food", content=b"foo,bar,baz\n1,2,3\n", filename="garbage.csv")
    assert resp.status_code == 422
    assert _rows(engine) == []


def test_import_requires_auth(engine):
    app.dependency_overrides.clear()
    resp = TestClient(app).post(
        "/import/food",
        files={"file": (_SAMPLE.name, _SAMPLE.read_bytes(), "text/csv")},
    )
    assert resp.status_code == 401
