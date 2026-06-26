"""Минимальный («быстрый») лог тренировки (S3.11): POST /workouts/simple + медиа.

Закрывает: тип/длительность/усилие пишутся прямо в сессию (без подходов); медиа (фото/видео)
кладётся на диск и отдаётся обратно по GET /workouts/media/{id}; валидация типа/длительности/RPE.
Медиа-каталог и BACKEND_DIR монкейпатчатся в tmp, чтобы тест не писал в репозиторий.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401 — регистрирует все таблицы в SQLModel.metadata
from app.core import db
from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.user import User

EMAIL = "simple@example.com"
PASSWORD = "right-password"


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(autouse=True)
def media_dir(tmp_path, monkeypatch):
    """Пишем медиа в tmp; BACKEND_DIR тоже tmp — чтобы relative_to() в эндпоинте сошёлся."""
    target = tmp_path / "uploads" / "workouts"
    target.mkdir(parents=True)
    monkeypatch.setattr(db, "BACKEND_DIR", tmp_path)
    monkeypatch.setattr(db, "workout_media_dir", lambda: target)


@pytest.fixture
def client(engine):
    with Session(engine) as session:
        session.add(User(email=EMAIL, password_hash=hash_password(PASSWORD)))
        session.commit()

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    test_client = TestClient(app)
    test_client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    yield test_client
    app.dependency_overrides.clear()


def test_simple_workout_without_media(client):
    res = client.post(
        "/workouts/simple",
        data={"kind": "cardio", "duration_min": "30", "rpe": "7", "note": "утренний бег", "date": "2026-06-24"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["kind"] == "cardio"
    assert body["duration_min"] == 30
    assert body["rpe"] == 7
    assert body["notes"] == "утренний бег"
    assert body["date"] == "2026-06-24"
    assert body["media"] == []


def test_simple_workout_stores_welltory_metrics(client):
    """Метрики Welltory (ядро 9671) сохраняются и возвращаются; и их одних достаточно как
    «начинки» — без длительности/заметки/медиа."""
    res = client.post(
        "/workouts/simple",
        data={
            "kind": "strength",
            "total_kcal": "573",
            "active_kcal": "489",
            "total_met": "509",
            "useful_met": "241",
            "hr_avg": "123",
            "hr_max": "162",
            "load_pct": "-8",
            "score": "3",
        },
    )
    assert res.status_code == 201, res.text
    b = res.json()
    assert b["duration_min"] is None  # только метрики — всё равно приняли
    assert (b["total_kcal"], b["active_kcal"]) == (573, 489)
    assert (b["total_met"], b["useful_met"]) == (509, 241)
    assert (b["hr_avg"], b["hr_max"], b["load_pct"], b["score"]) == (123, 162, -8, 3)


def test_simple_workout_media_only_no_duration(client):
    """Видео рекорда/трюка без длительности — длительность опциональна, медиа достаточно."""
    res = client.post(
        "/workouts/simple",
        data={"kind": "skill"},
        files=[("files", ("trick.png", b"\x89PNG\r\n\x1a\nfakebytes", "image/png"))],
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["duration_min"] is None
    media = body["media"]
    assert len(media) == 1
    assert media[0]["media_type"] == "image"

    # файл отдаётся обратно
    got = client.get(f"/workouts/media/{media[0]['id']}")
    assert got.status_code == 200
    assert got.content == b"\x89PNG\r\n\x1a\nfakebytes"


def test_simple_workout_accepts_phone_formats(client):
    """Телефонные форматы: HEIC-фото и HEVC .mov-видео принимаются (как accept=image/*,video/*)."""
    heic = client.post(
        "/workouts/simple",
        data={"kind": "other"},
        files=[("files", ("photo.heic", b"\x00\x00\x00\x18ftypheic", "image/heic"))],
    )
    assert heic.status_code == 201, heic.text
    assert heic.json()["media"][0]["media_type"] == "image"

    mov = client.post(
        "/workouts/simple",
        data={"kind": "skill"},
        files=[("files", ("trick.mov", b"\x00\x00\x00\x18ftypqt", "video/quicktime"))],
    )
    assert mov.status_code == 201, mov.text
    assert mov.json()["media"][0]["media_type"] == "video"

    # не медиа (документ) — отклоняем
    pdf = client.post(
        "/workouts/simple",
        data={"kind": "other"},
        files=[("files", ("plan.pdf", b"%PDF-1.4", "application/pdf"))],
    )
    assert pdf.status_code == 422


def test_simple_workout_validation(client):
    bad_kind = client.post("/workouts/simple", data={"kind": "yoga", "duration_min": "30"})
    assert bad_kind.status_code == 422

    bad_dur = client.post("/workouts/simple", data={"kind": "strength", "duration_min": "0"})
    assert bad_dur.status_code == 422

    bad_rpe = client.post(
        "/workouts/simple", data={"kind": "strength", "duration_min": "30", "rpe": "11"}
    )
    assert bad_rpe.status_code == 422

    # тип без начинки (нет ни длительности, ни заметки, ни медиа) — нечего сохранять
    empty = client.post("/workouts/simple", data={"kind": "strength"})
    assert empty.status_code == 422

    # только заметка — этого достаточно
    note_only = client.post("/workouts/simple", data={"kind": "other", "note": "лёгкая растяжка"})
    assert note_only.status_code == 201, note_only.text


def test_simple_workout_surpassed_self(client):
    """M2·B17: surpassed_self принимается формой, сохраняется и возвращается в ответе."""
    # по умолчанию (поле не прислано) — False
    default = client.post("/workouts/simple", data={"kind": "other", "note": "обычный день"})
    assert default.status_code == 201, default.text
    assert default.json()["surpassed_self"] is False

    # явный true — сохраняется и читается обратно
    flagged = client.post(
        "/workouts/simple",
        data={"kind": "skill", "note": "новый трюк", "surpassed_self": "true"},
    )
    assert flagged.status_code == 201, flagged.text
    body = flagged.json()
    assert body["surpassed_self"] is True

    # явный false — тоже уважается
    off = client.post(
        "/workouts/simple",
        data={"kind": "cardio", "duration_min": "20", "surpassed_self": "false"},
    )
    assert off.status_code == 201, off.text
    assert off.json()["surpassed_self"] is False


def test_media_404(client):
    assert client.get("/workouts/media/999").status_code == 404


def test_list_media_by_date(client):
    """M2·B18: GET /workouts/media?date= отдаёт media (id+type) сессий владельца за день."""
    # день с двумя медиа (одна сессия — фото, другая — видео)
    client.post(
        "/workouts/simple",
        data={"kind": "skill", "date": "2026-06-24"},
        files=[("files", ("a.png", b"\x89PNGfoto", "image/png"))],
    )
    client.post(
        "/workouts/simple",
        data={"kind": "skill", "date": "2026-06-24"},
        files=[("files", ("b.mov", b"\x00ftypqt vid", "video/quicktime"))],
    )
    # медиа другого дня — не должно попасть в выборку
    client.post(
        "/workouts/simple",
        data={"kind": "other", "date": "2026-06-25"},
        files=[("files", ("c.png", b"\x89PNGother", "image/png"))],
    )

    res = client.get("/workouts/media", params={"date": "2026-06-24"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body) == 2
    assert {m["media_type"] for m in body} == {"image", "video"}
    assert all(isinstance(m["id"], int) for m in body)

    # день без медиа — пустой список
    assert client.get("/workouts/media", params={"date": "2026-01-01"}).json() == []

    # date обязателен
    assert client.get("/workouts/media").status_code == 422
