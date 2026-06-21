"""Превью-сверка и сохранение выверенных полей активности Welltory (S1.11).

Закрывает критерии карточки:
- поля можно сверить с картинкой ПЕРЕД сохранением → /import/activity/preview
  возвращает распознанные поля и НИЧЕГО не пишет (ни записи, ни файла);
- правка поля сохраняется → /import/activity с формой `fields` пишет именно
  выверенные значения (vision при этом не дёргается).

Сеть не дёргаем: llm.vision замокан; каталог скринов — во временной папке.
"""

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

EMAIL = "preview@example.com"
PASSWORD = "right-password"

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
    target = tmp_path / "welltory"
    target.mkdir()
    monkeypatch.setattr(db, "welltory_dir", lambda: target)
    return target


@pytest.fixture(autouse=True)
def fake_vision(monkeypatch):
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


def _days(engine) -> list[ActivityDay]:
    with Session(engine) as session:
        return session.exec(select(ActivityDay)).all()


# ── Превью: сверка без записи ────────────────────────────────────────────────


def test_preview_returns_fields_without_saving(client, engine, uploads):
    resp = client.post(
        "/import/activity/preview",
        files={"file": ("day.png", PNG, "image/png")},
        data={"date": "2026-06-20"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # распознанные поля — рядом с которыми UI покажет картинку
    assert body["total_kcal"] == 1218
    assert body["steps"] == 4459
    assert body["moving_min"] == 173  # 2ч 53м
    assert body["raw_json"] == SCREEN_JSON
    assert body["saved"] is False
    # ничего не сохранено: ни записи в БД, ни файла на диске
    assert _days(engine) == []
    assert list(uploads.iterdir()) == []


def test_preview_invalid_vision_returns_422(client, engine, uploads, monkeypatch):
    monkeypatch.setattr(
        welltory.llm, "vision", lambda image_bytes, prompt, model=None: "не json вовсе"
    )
    resp = client.post("/import/activity/preview", files={"file": ("day.png", PNG, "image/png")})
    assert resp.status_code == 422
    assert _days(engine) == []


def test_preview_empty_file_returns_422(client, engine, uploads):
    resp = client.post("/import/activity/preview", files={"file": ("day.png", b"", "image/png")})
    assert resp.status_code == 422


# ── Сохранение выверенных полей ──────────────────────────────────────────────


def test_save_persists_edited_fields(client, engine, uploads):
    # пользователь поправил всего_ккал и шаги на шаге сверки
    edited = {
        "total_kcal": 1500,
        "active_kcal": 683,
        "steps": 5000,
        "moving_min": 173,
        "idle_min": 1317,
        "warmup_min": 420,
        "active_met": 782,
        "intense_met": 0,
    }
    resp = client.post(
        "/import/activity",
        files={"file": ("day.png", PNG, "image/png")},
        data={
            "date": "2026-06-20",
            "fields": json.dumps(edited),
            "raw_json": json.dumps(SCREEN_JSON, ensure_ascii=False),
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    # сохранены именно правки, а не разбор модели (1218 / 4459)
    assert body["total_kcal"] == 1500
    assert body["steps"] == 5000
    # raw_json хранит исходный разбор для аудита
    assert body["raw_json"] == SCREEN_JSON
    assert body["source_image_path"].endswith("2026-06-20.png")
    assert (uploads / "2026-06-20.png").read_bytes() == PNG

    rows = _days(engine)
    assert len(rows) == 1
    assert rows[0].total_kcal == 1500
    assert rows[0].steps == 5000


def test_save_edited_does_not_call_vision(client, engine, uploads, monkeypatch):
    # на шаге сохранения vision дёргать нельзя — поля уже выверены
    def boom(*args, **kwargs):  # pragma: no cover - срабатывает только при регрессии
        raise AssertionError("vision не должен вызываться при сохранении правок")

    monkeypatch.setattr(welltory.llm, "vision", boom)
    resp = client.post(
        "/import/activity",
        files={"file": ("day.png", PNG, "image/png")},
        data={"date": "2026-06-20", "fields": json.dumps({"total_kcal": 999})},
    )
    assert resp.status_code == 201
    assert resp.json()["total_kcal"] == 999


def test_save_edited_nulls_field(client, engine, uploads):
    # очищенное поле (плитки не было) сохраняется как null
    resp = client.post(
        "/import/activity",
        files={"file": ("day.png", PNG, "image/png")},
        data={"date": "2026-06-20", "fields": json.dumps({"total_kcal": None, "steps": 4459})},
    )
    assert resp.status_code == 201
    assert resp.json()["total_kcal"] is None
    assert resp.json()["steps"] == 4459


def test_save_invalid_fields_json_returns_422(client, engine, uploads):
    resp = client.post(
        "/import/activity",
        files={"file": ("day.png", PNG, "image/png")},
        data={"date": "2026-06-20", "fields": "{not json"},
    )
    assert resp.status_code == 422
    assert _days(engine) == []


def test_save_requires_auth(engine, uploads):
    app.dependency_overrides.clear()
    resp = TestClient(app).post(
        "/import/activity/preview",
        files={"file": ("day.png", PNG, "image/png")},
    )
    assert resp.status_code == 401
