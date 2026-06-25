"""Сервис видео-пруфов участия в челлендже (M6·B32): клон achievement_proof по participant_id.

Закрывает критерии карточки:
- services/challenge_proof.py: save_proof кладёт видео на диск, генерит превью (общий
  video_proof) и пишет challenge_proof(participant_id, video_path, thumbnail_path,
  uploaded_at, notes); has_proof отвечает, есть ли пруф у участия;
- challenge_proofs_dir в core/db.py: видео уходит в data/challenge_proofs/<participant_id>.
Плюс: notes опциональны; сбой ffmpeg → ThumbnailError, файл откатан, записи нет; один
интеграционный тест гоняет настоящий ffmpeg на реальном mp4.

Роутера/UI у карточки нет (модель + сервис) — тестируем сервис напрямую, как и сам
сервис вызывают (через сессию), без HTTP.
"""

import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401 — регистрирует таблицы в SQLModel.metadata
from app.core import db
from app.models.challenge import Challenge, ChallengeParticipant, ChallengeProof
from app.models.sport import Sport
from app.models.user import User
from app.services import challenge_proof as proof_service
from app.services import video_proof

# Не настоящее видео: для замоканного превью байты неважны, ffmpeg на них ломается.
FAKE_VIDEO = b"\x00\x00\x00\x18ftypmp42fake-video-bytes"

ffmpeg_required = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg не установлен в окружении"
)


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Sport(name="Бег", category="endurance"))  # sport.id == 1
        s.add(User(email="me@example.com", password_hash="h"))  # user.id == 1
        s.commit()
        s.add(
            Challenge(sport_id=1, creator_user_id=1, title="30 дней планки", description="Держи.")
        )
        s.commit()  # challenge.id == 1
        s.add(ChallengeParticipant(challenge_id=1, user_id=1))  # participant.id == 1
        s.commit()
        yield s


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


def _rows(session) -> list[ChallengeProof]:
    return session.exec(select(ChallengeProof)).all()


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


def test_save_proof_writes_video_thumbnail_and_row(session, proofs_dir, fake_thumb):
    # критерий: видео на диске; в БД participant_id + путь к видео + путь к превью + метаданные
    proof = proof_service.save_proof(
        session, 1, FAKE_VIDEO, filename="proof.mp4", notes="красиво подтянулся"
    )
    assert proof.id is not None
    assert proof.participant_id == 1
    assert proof.video_path.endswith(".mp4")
    assert proof.thumbnail_path.endswith(".jpg")
    assert proof.uploaded_at is not None
    assert proof.notes == "красиво подтянулся"
    # оба файла реально лежат на диске; в видео — исходные байты
    assert Path(proof.video_path).read_bytes() == FAKE_VIDEO
    assert Path(proof.thumbnail_path).exists()
    # ровно одна запись в challenge_proof
    rows = _rows(session)
    assert len(rows) == 1
    assert rows[0].participant_id == 1


def test_notes_optional(session, proofs_dir, fake_thumb):
    proof = proof_service.save_proof(session, 1, FAKE_VIDEO)
    assert proof.notes is None
    assert _rows(session)[0].notes is None


def test_has_proof_reflects_persisted_proof(session, proofs_dir, fake_thumb):
    assert proof_service.has_proof(session, 1) is False
    proof_service.save_proof(session, 1, FAKE_VIDEO)
    assert proof_service.has_proof(session, 1) is True
    # пруф другого участия не виден — has_proof скоупится по participant_id
    assert proof_service.has_proof(session, 2) is False


def test_thumbnail_failure_rolls_back(session, proofs_dir, monkeypatch):
    # сбой ffmpeg → ThumbnailError, видеофайл удалён, записи в БД нет
    def _boom(video_path, thumb_path):
        raise video_proof.ThumbnailError("битое видео")

    monkeypatch.setattr(video_proof, "_generate_thumbnail", _boom)
    with pytest.raises(proof_service.ThumbnailError):
        proof_service.save_proof(session, 1, FAKE_VIDEO)
    assert _rows(session) == []
    assert list((proofs_dir / "1").iterdir()) == []  # частичный видеофайл удалён


@ffmpeg_required
def test_real_ffmpeg_generates_thumbnail(session, proofs_dir, tmp_path):
    # критерий: превью генерируется — настоящий ffmpeg по настоящему mp4
    proof = proof_service.save_proof(session, 1, _make_mp4(tmp_path))
    thumb = Path(proof.thumbnail_path)
    assert thumb.exists() and thumb.stat().st_size > 0
    assert thumb.read_bytes()[:2] == b"\xff\xd8"  # настоящий JPEG (SOI-маркер)
