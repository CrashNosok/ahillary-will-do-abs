"""Эндпоинт ингеста скрина InBody (S2.11): сохранение замера + исходника.

Закрывает критерии карточки:
- POST /import/inbody сохраняет inbody_measurement с путём к скрину (source_image_path);
- пять промо-колонок + metrics_json пишутся в запись;
- POST /import/inbody/preview возвращает поля БЕЗ записи — «поля можно сверить перед
  сохранением», а форма fields сохраняет именно выверенные значения.
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
from app.models.body import InbodyMeasurement
from app.models.user import User
from app.services import inbody

EMAIL = "inbody@example.com"
PASSWORD = "right-password"

# Что vision-модель «вернёт» по скрину: пять ключевых ключей + прочие показатели.
SCREEN_JSON = {
    "вес": "75.3 kg",
    "процент_жира": "18.2 %",
    "мышечная_масса": "32.1 kg",
    "висцеральный_жир": "8",
    "вода": "45.6 L",
    "BMI": "23.4",
    "Базовый обмен": "1623 kcal",
}
METRICS_JSON = {"BMI": "23.4", "Базовый обмен": "1623 kcal"}
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
    target = tmp_path / "inbody"
    target.mkdir()
    monkeypatch.setattr(db, "inbody_dir", lambda: target)
    return target


@pytest.fixture(autouse=True)
def fake_vision(monkeypatch):
    """По умолчанию модель возвращает валидный разбор скрина — сеть не дёргаем."""
    monkeypatch.setattr(
        inbody.llm,
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


def _upload(client, *, date=None, content=PNG, filename="inbody.png", data=None):
    payload = dict(data or {})
    if date:
        payload["date"] = date
    return client.post(
        "/import/inbody",
        files={"file": (filename, content, "image/png")},
        data=payload,
    )


def _rows(engine) -> list[InbodyMeasurement]:
    with Session(engine) as session:
        return session.exec(select(InbodyMeasurement)).all()


def test_import_saves_measurement_with_image_path(client, engine, uploads):
    # критерий: запись сохранена с путём к скрину
    resp = _upload(client, date="2026-06-20")
    assert resp.status_code == 201
    body = resp.json()
    assert body["date"] == "2026-06-20"
    assert body["source_image_path"].endswith("2026-06-20.png")
    # файл реально записан на диск
    assert (uploads / "2026-06-20.png").read_bytes() == PNG
    # промо-колонки разобраны (единицы отрезаны)
    assert body["weight_kg"] == 75.3
    assert body["body_fat_pct"] == 18.2
    assert body["muscle_mass_kg"] == 32.1
    assert body["visceral_fat"] == 8.0
    assert body["water"] == 45.6

    rows = _rows(engine)
    assert len(rows) == 1
    assert str(rows[0].date) == "2026-06-20"
    assert rows[0].source_image_path.endswith("2026-06-20.png")
    assert rows[0].parsed_at is not None


def test_metrics_json_stores_other_metrics(client, engine, uploads):
    # критерий: прочие показатели уходят в metrics_json «как есть»
    resp = _upload(client, date="2026-06-20")
    assert resp.json()["metrics_json"] == METRICS_JSON
    assert _rows(engine)[0].metrics_json == METRICS_JSON


def test_preview_returns_fields_without_saving(client, engine, uploads):
    # критерий: поля можно сверить перед сохранением — превью НЕ пишет в БД
    resp = client.post(
        "/import/inbody/preview",
        files={"file": ("inbody.png", PNG, "image/png")},
        data={"date": "2026-06-20"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["saved"] is False
    assert body["weight_kg"] == 75.3
    assert body["metrics_json"] == METRICS_JSON
    # ни записи, ни файла — это только сверка
    assert _rows(engine) == []
    assert list(uploads.iterdir()) == []


def test_save_with_fields_persists_verified_values(client, engine, uploads):
    # критерий: сохраняются именно выверенные пользователем значения, vision не дёргается
    edited = {
        "weight_kg": 74.0,  # поправлено вручную
        "body_fat_pct": 18.2,
        "muscle_mass_kg": 32.1,
        "visceral_fat": 8.0,
        "water": 45.6,
    }
    resp = _upload(
        client,
        date="2026-06-20",
        data={"fields": json.dumps(edited), "metrics_json": json.dumps(METRICS_JSON)},
    )
    assert resp.status_code == 201
    assert resp.json()["weight_kg"] == 74.0
    rows = _rows(engine)
    assert rows[0].weight_kg == 74.0
    assert rows[0].metrics_json == METRICS_JSON


def test_reimport_same_day_replaces_not_duplicates(client, engine, uploads):
    _upload(client, date="2026-06-20")
    second = _upload(client, date="2026-06-20")
    assert second.status_code == 201
    assert len(_rows(engine)) == 1  # один день: заменён, не задублирован


def test_date_defaults_to_today(client, engine, uploads):
    resp = _upload(client)  # без поля date
    assert resp.status_code == 201
    today = dt.date.today().isoformat()
    assert resp.json()["date"] == today
    assert (uploads / f"{today}.png").exists()


def test_invalid_vision_response_returns_422(client, engine, uploads, monkeypatch):
    monkeypatch.setattr(
        inbody.llm,
        "vision",
        lambda image_bytes, prompt, model=None: "не json вовсе",
    )
    resp = _upload(client, date="2026-06-20")
    assert resp.status_code == 422
    # ни записи, ни файла — разбор провалился до сохранения
    assert _rows(engine) == []
    assert list(uploads.iterdir()) == []


def test_empty_file_returns_422(client, engine, uploads):
    resp = _upload(client, content=b"")
    assert resp.status_code == 422
    assert _rows(engine) == []


def test_import_requires_auth(engine, uploads):
    app.dependency_overrides.clear()
    resp = TestClient(app).post(
        "/import/inbody",
        files={"file": ("inbody.png", PNG, "image/png")},
    )
    assert resp.status_code == 401
