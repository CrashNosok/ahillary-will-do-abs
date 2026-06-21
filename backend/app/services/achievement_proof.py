"""Видео-пруфы ачивок (S5.4): файл на диск + ffmpeg-превью, в БД только пути/метаданные.

Видео кладётся в data/videos/<achievement_id>/<uuid>.<ext>, из него ffmpeg вытягивает
один кадр в <uuid>.jpg рядом. В achievement_proof пишутся относительные пути к обоим
файлам + uploaded_at (default) + notes. Сами байты в БД не хранятся.
"""

import subprocess
from pathlib import Path
from uuid import uuid4

from sqlmodel import Session, select

from app.core import db
from app.models.achievement import AchievementProof


def has_proof(session: Session, achievement_id: int) -> bool:
    """Есть ли у ачивки хотя бы один видео-пруф (правило закрытия S5.5)."""
    stmt = select(AchievementProof.id).where(AchievementProof.achievement_id == achievement_id)
    return session.exec(stmt.limit(1)).first() is not None


class ThumbnailError(RuntimeError):
    """ffmpeg не смог сгенерировать превью (нет ffmpeg в PATH либо битое/не-видео)."""


def _generate_thumbnail(video_path: Path, thumb_path: Path) -> None:
    """Вытягивает кадр видео в JPEG через ffmpeg. Любой сбой → ThumbnailError."""
    # ponytail: первый кадр; representative-кадр (-vf thumbnail) если первый окажется чёрным.
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-update",
                "1",
                str(thumb_path),
            ],
            capture_output=True,
        )
    except FileNotFoundError as exc:  # ffmpeg не установлен
        raise ThumbnailError("ffmpeg не найден в PATH") from exc
    if result.returncode != 0 or not thumb_path.exists() or thumb_path.stat().st_size == 0:
        detail = result.stderr.decode("utf-8", "replace").strip() or "пустое превью"
        raise ThumbnailError(detail)


def _rel(path: Path) -> str:
    """Путь относительно backend/ — чтобы в БД не текли абсолютные пути окружения."""
    try:
        return str(path.relative_to(db.BACKEND_DIR))
    except ValueError:  # каталог данных вне backend/ (абсолютный DATA_DIR) — храним как есть
        return str(path)


def save_proof(
    session: Session,
    achievement_id: int,
    video_bytes: bytes,
    *,
    filename: str | None = None,
    notes: str | None = None,
) -> AchievementProof:
    """Сохранить видео + превью на диск и записать achievement_proof (S5.4).

    Превью генерируется ДО записи в БД: если ffmpeg упал — видеофайл удаляется и
    записи не появляется (ThumbnailError пробрасывается, HTTP-код выбирает роут).
    """
    target_dir = db.videos_dir(achievement_id)
    stem = uuid4().hex
    ext = Path(filename or "").suffix or ".mp4"
    video_dest = target_dir / f"{stem}{ext}"
    thumb_dest = target_dir / f"{stem}.jpg"

    video_dest.write_bytes(video_bytes)
    try:
        _generate_thumbnail(video_dest, thumb_dest)
    except ThumbnailError:
        video_dest.unlink(missing_ok=True)
        raise

    proof = AchievementProof(
        achievement_id=achievement_id,
        video_path=_rel(video_dest),
        thumbnail_path=_rel(thumb_dest),
        notes=notes,
    )
    session.add(proof)
    session.commit()
    session.refresh(proof)
    return proof
