"""Общий механизм видео-пруфов (M6·B32): байты видео → файл на диск + ffmpeg-превью.

Видео и его превью кладутся в переданный каталог как <uuid>.<ext> и <uuid>.jpg;
наружу возвращаются ОТНОСИТЕЛЬНЫЕ (от backend/) пути к обоим файлам — в БД пишут
именно их, а не байты. Превью генерируется ДО возврата: если ffmpeg упал, видеофайл
удаляется и ThumbnailError пробрасывается (HTTP-код выбирает вызывающий код).

Используется и ачивками (services.achievement_proof), и челленджами
(services.challenge_proof) — таблицы пруфов у них свои, а механика файлов общая.
"""

import subprocess
from pathlib import Path
from uuid import uuid4

from app.core import db

# Безопасные расширения видео (имя файла приходит от клиента — не доверяем суффиксу).
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
# Потолок размера загружаемого видео — защита от OOM/DoS при чтении в память.
MAX_VIDEO_BYTES = 500 * 1024 * 1024  # 500 МБ


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


def save_video_with_thumbnail(
    target_dir: Path, video_bytes: bytes, *, filename: str | None = None
) -> tuple[str, str]:
    """Сохранить видео + превью в target_dir; вернуть относительные пути (video, thumbnail).

    Превью генерируется ДО возврата: если ffmpeg упал — видеофайл удаляется и
    ThumbnailError пробрасывается, чтобы вызывающий не записал в БД пруф без файлов.
    Запись в БД — на стороне вызывающего, уже после успешного возврата.
    """
    stem = uuid4().hex
    # Расширение — из allowlist видеоформатов; всё прочее (включая .php/.svg/.html и т.п.)
    # сводим к .mp4, чтобы не писать на диск исполняемые/опасные суффиксы из имени клиента.
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        ext = ".mp4"
    video_dest = target_dir / f"{stem}{ext}"
    thumb_dest = target_dir / f"{stem}.jpg"

    video_dest.write_bytes(video_bytes)
    try:
        _generate_thumbnail(video_dest, thumb_dest)
    except ThumbnailError:
        video_dest.unlink(missing_ok=True)
        raise
    return _rel(video_dest), _rel(thumb_dest)
