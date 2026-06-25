"""Видео-пруфы участия в челлендже (M6·B32): запись challenge_proof по participant_id.

Клон achievement_proof, но привязка к участию через FK participant_id
(challenge_participant.id). Механика файлов (видео на диск + ffmpeg-превью,
относительные пути в БД) — общий services.video_proof. Видео кладётся в
data/challenge_proofs/<participant_id>/, в БД пишутся пути + uploaded_at + notes.
"""

from sqlmodel import Session, select

from app.core import db
from app.models.challenge import ChallengeProof
from app.services import video_proof

# Совместимость с achievement_proof: вызывающий ловит proof_service.ThumbnailError.
ThumbnailError = video_proof.ThumbnailError

__all__ = ["ThumbnailError", "has_proof", "save_proof"]


def has_proof(session: Session, participant_id: int) -> bool:
    """Есть ли у участия хотя бы один видео-пруф."""
    stmt = select(ChallengeProof.id).where(ChallengeProof.participant_id == participant_id)
    return session.exec(stmt.limit(1)).first() is not None


def save_proof(
    session: Session,
    participant_id: int,
    video_bytes: bytes,
    *,
    filename: str | None = None,
    notes: str | None = None,
) -> ChallengeProof:
    """Сохранить видео + превью на диск и записать challenge_proof.

    Файлы и превью пишет общий video_proof; при сбое ffmpeg он пробрасывает
    ThumbnailError — записи в БД при этом не появляется.
    """
    video_path, thumbnail_path = video_proof.save_video_with_thumbnail(
        db.challenge_proofs_dir(participant_id), video_bytes, filename=filename
    )
    proof = ChallengeProof(
        participant_id=participant_id,
        video_path=video_path,
        thumbnail_path=thumbnail_path,
        notes=notes,
    )
    session.add(proof)
    session.commit()
    session.refresh(proof)
    return proof
