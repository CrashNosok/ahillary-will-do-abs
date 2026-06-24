"""Эндпоинт импорта скрина активности Welltory (S1.10): сохранение дня + исходника.

Закрывает критерии карточки:
- POST /import/activity сохраняет день активности с путём к скрину;
- raw_json хранит полный разбор vision-модели.
Плюс: файл реально лёг на диск, идемпотентность по дню, дефолт-дата = сегодня,
битый ответ модели → 422, роут под авторизацией.

Сеть не дёргаем: llm.vision замокан; каталог скринов — во временной папке.
"""

import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401 — регистрирует таблицы в SQLModel.metadata
from app.core import db
from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.activity import ActivityDay
from app.models.user import User
from app.services import welltory

EMAIL = "activity@example.com"
PASSWORD = "right-password"

# Что vision-модель «вернёт» по скрину (плитки IMG_9605.PNG, см. test_welltory).
SCREEN_JSON = {
    "всего_ккал": "1218 ккал",
    "активные_ккал": "683 ккал",
    "шаги": "4459",
    "в_движении": "2ч 53м",
    "без_движения": "21ч 57м",
    "разминка": "7ч",
    "активные_мет": "782 МЕТ",
    "интенсивные_мет": "0 МЕТ",
}
PNG = b"\x89PNG\r\n\x1a\nfake-image-bytes"


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
def uploads(tmp_path, monkeypatch):
    """Каталог скринов во временной папке — не пишем в реальный backend/data."""
    target = tmp_path / "welltory"
    target.mkdir()
    monkeypatch.setattr(db, "welltory_dir", lambda: target)
    return target


@pytest.fixture(autouse=True)
def fake_vision(monkeypatch):
    """По умолчанию модель возвращает валидный разбор скрина — сеть не дёргаем."""
    monkeypatch.setattr(
        welltory.llm,
        "vision",
        lambda image_bytes, prompt, model=None: json.dumps(SCREEN_JSON, ensure_ascii=False),
    )


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


def _upload(client, *, date=None, content=PNG, filename="day.png"):
    data = {"date": date} if date else {}
    return client.post(
        "/import/activity",
        files={"file": (filename, content, "image/png")},
        data=data,
    )


def _days(engine) -> list[ActivityDay]:
    with Session(engine) as session:
        return session.exec(select(ActivityDay)).all()


def test_import_saves_day_with_image_path(client, engine, uploads):
    # критерий: день активности сохранён с путём к скрину
    resp = _upload(client, date="2026-06-20")
    assert resp.status_code == 201
    body = resp.json()
    assert body["date"] == "2026-06-20"
    assert body["source_image_path"].endswith("2026-06-20.png")
    # файл реально записан на диск
    assert (uploads / "2026-06-20.png").read_bytes() == PNG
    # нормализованные поля разбора сохранены
    assert body["total_kcal"] == 1218
    assert body["steps"] == 4459
    assert body["moving_min"] == 173  # 2ч 53м

    rows = _days(engine)
    assert len(rows) == 1
    assert str(rows[0].date) == "2026-06-20"
    assert rows[0].source_image_path.endswith("2026-06-20.png")
    assert rows[0].parsed_at is not None


def test_manual_entry_saves_day_without_image(client, engine):
    # ручной ввод (без скрина): день сохранён, source_image_path пуст, vision не дёргался
    resp = client.post(
        "/import/activity/manual",
        json={"date": "2026-06-21", "total_kcal": 1123, "active_kcal": 24, "steps": 775},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["date"] == "2026-06-21"
    assert body["total_kcal"] == 1123 and body["active_kcal"] == 24 and body["steps"] == 775
    assert body["source_image_path"] is None
    rows = _days(engine)
    assert len(rows) == 1 and str(rows[0].date) == "2026-06-21"
    assert rows[0].raw_json == {"manual": True}


def test_raw_json_stores_full_parse(client, engine, uploads):
    # критерий: raw_json хранит полный разбор (все восемь плиток как вернула модель)
    resp = _upload(client, date="2026-06-20")
    assert resp.json()["raw_json"] == SCREEN_JSON
    assert _days(engine)[0].raw_json == SCREEN_JSON


def test_reimport_same_day_replaces_not_duplicates(client, engine, uploads):
    _upload(client, date="2026-06-20")
    second = _upload(client, date="2026-06-20")
    assert second.status_code == 201
    assert len(_days(engine)) == 1  # один день: заменён, не задублирован


def test_date_defaults_to_today(client, engine, uploads):
    resp = _upload(client)  # без поля date
    assert resp.status_code == 201
    today = dt.date.today().isoformat()
    assert resp.json()["date"] == today
    assert (uploads / f"{today}.png").exists()


def test_invalid_vision_response_returns_422(client, engine, uploads, monkeypatch):
    monkeypatch.setattr(
        welltory.llm,
        "vision",
        lambda image_bytes, prompt, model=None: "не json вовсе",
    )
    resp = _upload(client, date="2026-06-20")
    assert resp.status_code == 422
    # ни записи, ни файла — разбор провалился до сохранения
    assert _days(engine) == []
    assert list(uploads.iterdir()) == []


def test_empty_file_returns_422(client, engine, uploads):
    resp = _upload(client, content=b"")
    assert resp.status_code == 422
    assert _days(engine) == []


def test_import_requires_auth(engine, uploads):
    app.dependency_overrides.clear()
    resp = TestClient(app).post(
        "/import/activity",
        files={"file": ("day.png", PNG, "image/png")},
    )
    assert resp.status_code == 401
