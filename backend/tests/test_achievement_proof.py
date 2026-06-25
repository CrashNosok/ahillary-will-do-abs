"""Эндпоинт видео-пруфа ачивки (S5.4): видео на диск, превью через ffmpeg, пути в БД.

Закрывает критерии карточки:
- видео реально лежит на диске, в achievement_proof пишутся путь к видео + путь к превью
  + метаданные (uploaded_at, notes);
- превью генерируется (реальный ffmpeg по настоящему mp4).
Плюс: неизвестная ачивка → 404, пустой файл → 422, битое видео → 422 (ffmpeg не смог)
без записи в БД и с откатом файла, роут под авторизацией.

ffmpeg-путь покрыт двумя способами: быстрые тесты мокают генерацию превью (детерминизм,
независимость от ffmpeg), один интеграционный тест гоняет настоящий ffmpeg на mp4.
"""

import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401 — регистрирует таблицы в SQLModel.metadata
from app.core import db
from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models.achievement import Achievement, AchievementProof
from app.models.user import User
from app.services import achievement_proof as proof_service

EMAIL = "proof@example.com"
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
        session.add(User(email=EMAIL, password_hash=hash_password(PASSWORD)))
        session.add(Achievement(id=1, user_id=1, sport_id=None, title="Первый подтяг"))
        session.commit()
    return eng


@pytest.fixture
def videos(tmp_path, monkeypatch):
    """Каталоги видео во временной папке — не пишем в реальный backend/data."""
    base = tmp_path / "videos"

    def _dir(achievement_id):
        target = base / str(achievement_id)
        target.mkdir(parents=True, exist_ok=True)
        return target

    monkeypatch.setattr(db, "videos_dir", _dir)
    return base


@pytest.fixture
def fake_thumb(monkeypatch):
    """Подменяет ffmpeg-генерацию заглушкой-JPEG — быстрые тесты не зависят от ffmpeg."""

    def _fake(video_path, thumb_path):
        thumb_path.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")

    monkeypatch.setattr(proof_service, "_generate_thumbnail", _fake)


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


def _upload(client, *, content=FAKE_VIDEO, filename="proof.mp4", achievement_id=1, data=None):
    return client.post(
        f"/achievements/{achievement_id}/proofs",
        files={"file": (filename, content, "video/mp4")},
        data=data or {},
    )


def _rows(engine) -> list[AchievementProof]:
    with Session(engine) as session:
        return session.exec(select(AchievementProof)).all()


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


def test_upload_saves_video_and_thumbnail_paths(client, engine, videos, fake_thumb):
    # критерий: видео на диске; в БД путь к видео + путь к превью + метаданные
    from pathlib import Path

    resp = _upload(client, data={"notes": "красиво подтянулся"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["achievement_id"] == 1
    assert body["video_path"].endswith(".mp4")
    assert body["thumbnail_path"].endswith(".jpg")
    assert body["uploaded_at"] is not None
    assert body["notes"] == "красиво подтянулся"
    # оба файла реально лежат на диске; в видео — исходные байты
    assert Path(body["video_path"]).read_bytes() == FAKE_VIDEO
    assert Path(body["thumbnail_path"]).exists()

    rows = _rows(engine)
    assert len(rows) == 1
    assert rows[0].achievement_id == 1
    assert rows[0].video_path.endswith(".mp4")
    assert rows[0].thumbnail_path.endswith(".jpg")
    assert rows[0].uploaded_at is not None
    assert rows[0].notes == "красиво подтянулся"


def test_notes_optional(client, engine, videos, fake_thumb):
    # метаданные опциональны: без notes запись всё равно создаётся
    resp = _upload(client)
    assert resp.status_code == 201
    assert resp.json()["notes"] is None
    assert _rows(engine)[0].notes is None


def test_unknown_achievement_returns_404(client, engine, videos, fake_thumb):
    resp = _upload(client, achievement_id=999)
    assert resp.status_code == 404
    assert _rows(engine) == []


def test_empty_file_returns_422(client, engine, videos, fake_thumb):
    resp = _upload(client, content=b"")
    assert resp.status_code == 422
    assert _rows(engine) == []


@ffmpeg_required
def test_broken_video_returns_422_and_rolls_back(client, engine, videos):
    # реальный ffmpeg на мусоре падает → 422, записи нет, видеофайл откатан
    resp = _upload(client, content=FAKE_VIDEO)
    assert resp.status_code == 422
    assert _rows(engine) == []
    assert list((videos / "1").iterdir()) == []  # частичный видеофайл удалён


@ffmpeg_required
def test_real_ffmpeg_generates_thumbnail(client, engine, videos, tmp_path):
    # критерий: превью генерируется — настоящий ffmpeg по настоящему mp4
    from pathlib import Path

    resp = _upload(client, content=_make_mp4(tmp_path))
    assert resp.status_code == 201
    thumb = Path(resp.json()["thumbnail_path"])
    assert thumb.exists() and thumb.stat().st_size > 0
    assert thumb.read_bytes()[:2] == b"\xff\xd8"  # настоящий JPEG (SOI-маркер)


def test_upload_requires_auth(engine, videos):
    app.dependency_overrides.clear()
    resp = TestClient(app).post(
        "/achievements/1/proofs",
        files={"file": ("proof.mp4", FAKE_VIDEO, "video/mp4")},
    )
    assert resp.status_code == 401
