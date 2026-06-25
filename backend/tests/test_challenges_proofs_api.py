"""Челлендж: видео-пруф участия + переходы статуса (M6·B35).

POST /challenges/{id}/proofs — текущий участник грузит видео; ffmpeg-превью через общий
video_proof, в challenge_proof пишутся пути + метаданные (байты не в БД). Привязка к
участию текущего пользователя в челлендже {id}.

PATCH /challenges/{id}/participation — переход статуса участника. Допустимые переходы:
active → {completed, abandoned}, abandoned → {active}; completed терминален. Переход в
completed = «verify»: требует хотя бы один видео-пруф (409 без него).

Залогинен user(id=1). ffmpeg-путь покрыт мокнутым превью (детерминизм), один
интеграционный тест гоняет настоящий ffmpeg на реальном mp4.
"""

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401 — регистрирует все таблицы в SQLModel.metadata
from app.core import db
from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.challenge import ChallengeProof
from app.models.sport import Sport
from app.models.user import User
from app.services import video_proof

EMAIL = "challenger@example.com"
PASSWORD = "right-password"
# Не настоящее видео: для замоканного превью байты неважны, ffmpeg на них ломается.
FAKE_VIDEO = b"\x00\x00\x00\x18ftypmp42fake-video-bytes"

ffmpeg_required = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg не установлен в окружении"
)


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    with Session(eng) as session:
        session.add(User(email=EMAIL, password_hash=hash_password(PASSWORD)))  # id=1
        session.commit()
    return eng


@pytest.fixture
def proofs_dir(tmp_path, monkeypatch):
    """Каталог пруфов во временной папке — не пишем в реальный backend/data."""
    base = tmp_path / "challenge_proofs"

    def _dir(participant_id):
        target = base / str(participant_id)
        target.mkdir(parents=True, exist_ok=True)
        return target

    monkeypatch.setattr(db, "challenge_proofs_dir", _dir)
    return base


@pytest.fixture
def fake_thumb(monkeypatch):
    """Подменяет ffmpeg-генерацию заглушкой-JPEG — быстрые тесты не зависят от ffmpeg."""

    def _fake(video_path, thumb_path):
        thumb_path.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")

    monkeypatch.setattr(video_proof, "_generate_thumbnail", _fake)


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


def _make_sport(engine, name: str, category: str = "strength") -> int:
    with Session(engine) as session:
        sport = Sport(name=name, category=category)
        session.add(sport)
        session.commit()
        session.refresh(sport)
        return sport.id


def _make_challenge(client, engine, *, title="30 дней планки") -> int:
    sid = _make_sport(engine, f"спорт-{title}")
    return client.post(
        "/challenges", json={"sport_id": sid, "title": title, "description": "держи"}
    ).json()["id"]


def _join(client, engine, **kw) -> int:
    """Создать челлендж и вступить в него; вернуть challenge_id."""
    cid = _make_challenge(client, engine, **kw)
    assert client.post(f"/challenges/{cid}/join").status_code == 201
    return cid


def _upload(client, challenge_id, *, content=FAKE_VIDEO, filename="proof.mp4", data=None):
    return client.post(
        f"/challenges/{challenge_id}/proofs",
        files={"file": (filename, content, "video/mp4")},
        data=data or {},
    )


def _proof_rows(engine) -> list[ChallengeProof]:
    with Session(engine) as session:
        return session.exec(select(ChallengeProof)).all()


# ── upload proof ──────────────────────────────────────────────────────────────


def test_upload_proof_returns_201_and_persists(client, engine, proofs_dir, fake_thumb):
    cid = _join(client, engine)
    resp = _upload(client, cid, data={"notes": "держал 5 минут"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["participant_id"] is not None
    assert body["video_path"].endswith(".mp4")
    assert body["thumbnail_path"].endswith(".jpg")
    assert body["uploaded_at"] is not None
    assert body["notes"] == "держал 5 минут"
    # оба файла реально лежат на диске; в видео — исходные байты
    assert Path(body["video_path"]).read_bytes() == FAKE_VIDEO
    assert Path(body["thumbnail_path"]).exists()
    rows = _proof_rows(engine)
    assert len(rows) == 1
    assert rows[0].notes == "держал 5 минут"


def test_upload_proof_notes_optional(client, engine, proofs_dir, fake_thumb):
    cid = _join(client, engine)
    resp = _upload(client, cid)
    assert resp.status_code == 201
    assert resp.json()["notes"] is None


def test_upload_proof_not_joined_returns_404(client, engine, proofs_dir, fake_thumb):
    # челлендж есть, но пользователь в нём не участвует → 404, записи нет
    cid = _make_challenge(client, engine)
    resp = _upload(client, cid)
    assert resp.status_code == 404
    assert _proof_rows(engine) == []


def test_upload_proof_unknown_challenge_returns_404(client, engine, proofs_dir, fake_thumb):
    resp = _upload(client, 999)
    assert resp.status_code == 404
    assert _proof_rows(engine) == []


def test_upload_proof_empty_file_returns_422(client, engine, proofs_dir, fake_thumb):
    cid = _join(client, engine)
    resp = _upload(client, cid, content=b"")
    assert resp.status_code == 422
    assert _proof_rows(engine) == []


def test_upload_proof_thumbnail_failure_returns_422_and_rolls_back(
    client, engine, proofs_dir, monkeypatch
):
    cid = _join(client, engine)

    def _boom(video_path, thumb_path):
        raise video_proof.ThumbnailError("битое видео")

    monkeypatch.setattr(video_proof, "_generate_thumbnail", _boom)
    resp = _upload(client, cid)
    assert resp.status_code == 422
    assert _proof_rows(engine) == []
    assert list((proofs_dir / "1").iterdir()) == []  # частичный видеофайл удалён


# ── status transitions ────────────────────────────────────────────────────────


def _set_status(client, challenge_id, status):
    return client.patch(f"/challenges/{challenge_id}/participation", json={"status": status})


def test_status_active_to_abandoned(client, engine):
    cid = _join(client, engine)
    resp = _set_status(client, cid, "abandoned")
    assert resp.status_code == 200
    assert resp.json()["status"] == "abandoned"


def test_status_abandoned_back_to_active(client, engine):
    cid = _join(client, engine)
    assert _set_status(client, cid, "abandoned").status_code == 200
    resp = _set_status(client, cid, "active")
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


def test_complete_without_proof_returns_409(client, engine):
    cid = _join(client, engine)
    resp = _set_status(client, cid, "completed")
    assert resp.status_code == 409  # verify: нет пруфа — нельзя завершить


def test_complete_with_proof_returns_200(client, engine, proofs_dir, fake_thumb):
    cid = _join(client, engine)
    assert _upload(client, cid).status_code == 201
    resp = _set_status(client, cid, "completed")
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


def test_completed_is_terminal_returns_409(client, engine, proofs_dir, fake_thumb):
    cid = _join(client, engine)
    assert _upload(client, cid).status_code == 201
    assert _set_status(client, cid, "completed").status_code == 200
    # completed → active недопустим (терминальный статус)
    assert _set_status(client, cid, "active").status_code == 409


def test_invalid_status_value_returns_422(client, engine):
    cid = _join(client, engine)
    assert _set_status(client, cid, "winner").status_code == 422


def test_status_not_joined_returns_404(client, engine):
    cid = _make_challenge(client, engine)
    assert _set_status(client, cid, "abandoned").status_code == 404


def test_status_unknown_challenge_returns_404(client, engine):
    assert _set_status(client, 999, "abandoned").status_code == 404


# ── auth ──────────────────────────────────────────────────────────────────────


def test_proof_and_status_require_auth(engine):
    app.dependency_overrides.clear()
    unauth = TestClient(app)
    proof = unauth.post("/challenges/1/proofs", files={"file": ("p.mp4", FAKE_VIDEO, "video/mp4")})
    assert proof.status_code == 401
    status_resp = unauth.patch("/challenges/1/participation", json={"status": "abandoned"})
    assert status_resp.status_code == 401


# ── real ffmpeg ───────────────────────────────────────────────────────────────


def _make_mp4(tmp_path) -> bytes:
    """Генерит крошечный настоящий mp4 через ffmpeg lavfi — для интеграционного теста."""
    out = tmp_path / "src.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=1:size=64x64:rate=10",
            "-pix_fmt",
            "yuv420p",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    return out.read_bytes()


@ffmpeg_required
def test_real_ffmpeg_generates_thumbnail(client, engine, proofs_dir, tmp_path):
    cid = _join(client, engine)
    resp = _upload(client, cid, content=_make_mp4(tmp_path))
    assert resp.status_code == 201
    thumb = Path(resp.json()["thumbnail_path"])
    assert thumb.exists() and thumb.stat().st_size > 0
    assert thumb.read_bytes()[:2] == b"\xff\xd8"  # настоящий JPEG (SOI-маркер)
