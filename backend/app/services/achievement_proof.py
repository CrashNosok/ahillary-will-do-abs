"""Видео-пруфы ачивок (S5.4): запись achievement_proof по achievement_id.

Механика файлов (видео на диск + ffmpeg-превью, относительные пути в БД) вынесена в
общий services.video_proof (M6·B32). Здесь — только запись в таблицу achievement_proof:
видео кладётся в data/videos/<achievement_id>/, в БД пишутся пути + uploaded_at + notes.
"""

from sqlmodel import Session, select

from app.core import db
from app.models.achievement import AchievementProof
from app.services import video_proof

# Совместимость: роут и тесты ловят proof_service.ThumbnailError (та же, что в video_proof).
ThumbnailError = video_proof.ThumbnailError

__all__ = ["ThumbnailError", "has_proof", "save_proof"]


def has_proof(session: Session, achievement_id: int) -> bool:
    """Есть ли у ачивки хотя бы один видео-пруф (правило закрытия S5.5)."""
    stmt = select(AchievementProof.id).where(AchievementProof.achievement_id == achievement_id)
    return session.exec(stmt.limit(1)).first() is not None


def save_proof(
    session: Session,
    achievement_id: int,
    video_bytes: bytes,
    *,
    filename: str | None = None,
    notes: str | None = None,
) -> AchievementProof:
    """Сохранить видео + превью на диск и записать achievement_proof (S5.4).

    Файлы и превью пишет общий video_proof; при сбое ffmpeg он пробрасывает
    ThumbnailError (HTTP-код выбирает роут) — записи в БД при этом не появляется.
    """
    video_path, thumbnail_path = video_proof.save_video_with_thumbnail(
        db.videos_dir(achievement_id), video_bytes, filename=filename
    )
    proof = AchievementProof(
        achievement_id=achievement_id,
        video_path=video_path,
        thumbnail_path=thumbnail_path,
        notes=notes,
    )
    session.add(proof)
    session.commit()
    session.refresh(proof)
    return proof
