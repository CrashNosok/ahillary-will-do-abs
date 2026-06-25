"""Челленджи (M6·B34): создание/список + участие (join). Пруф + статус (M6·B35).

POST /challenges — завести вызов; creator_user_id берётся из сессии (а не из тела).
GET /challenges — каталог всех челленджей (их находят и присоединяются), по заголовку.
POST /challenges/{id}/join — стать участником: создаёт challenge_participant(user_id=me).
POST /challenges/{id}/proofs — участник грузит видео-пруф (ffmpeg-превью через общий
video_proof); в challenge_proof пишутся пути + метаданные (байты в БД не хранятся).
PATCH /challenges/{id}/participation — переход статуса участника: active → {completed,
abandoned}, abandoned → {active}, completed терминален. Переход в completed = «verify»:
требует хотя бы один видео-пруф (409 без него).
Все роуты под сессией (CurrentUser). is_base не выставляется пользователем — базовые
(встроенные) челленджи заводятся отдельно; обычное создание даёт пользовательский (False).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.models.challenge import (
    Challenge,
    ChallengeParticipant,
    ChallengeParticipantStatus,
    ChallengeProof,
)
from app.models.sport import Sport
from app.services import challenge_proof as proof_service

router = APIRouter(prefix="/challenges", tags=["challenges"])

SessionDep = Annotated[Session, Depends(get_session)]

# Допустимые переходы статуса участника. completed терминален; переход в completed
# дополнительно требует видео-пруф (см. update_participation_status).
_ALLOWED_TRANSITIONS: dict[ChallengeParticipantStatus, set[ChallengeParticipantStatus]] = {
    ChallengeParticipantStatus.active: {
        ChallengeParticipantStatus.completed,
        ChallengeParticipantStatus.abandoned,
    },
    ChallengeParticipantStatus.abandoned: {ChallengeParticipantStatus.active},
    ChallengeParticipantStatus.completed: set(),
}


class ChallengeCreate(BaseModel):
    sport_id: int
    title: str
    description: str


class ParticipationUpdate(BaseModel):
    status: ChallengeParticipantStatus  # невалидное значение → 422 (валидирует Pydantic)


def _my_participation_or_404(
    session: Session, challenge_id: int, user_id: int
) -> ChallengeParticipant:
    """Участие текущего пользователя в челлендже или 404 (нет челленджа / не вступил)."""
    if session.get(Challenge, challenge_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Челлендж не найден")
    participant = session.exec(
        select(ChallengeParticipant).where(
            ChallengeParticipant.challenge_id == challenge_id,
            ChallengeParticipant.user_id == user_id,
        )
    ).first()
    if participant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Вы не участвуете в челлендже"
        )
    return participant


@router.post("", status_code=status.HTTP_201_CREATED)
def create_challenge(payload: ChallengeCreate, session: SessionDep, user: CurrentUser) -> Challenge:
    """Завести челлендж. creator_user_id — из сессии. 404 — нет такого вида спорта."""
    if session.get(Sport, payload.sport_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Вид спорта не найден")
    challenge = Challenge(
        sport_id=payload.sport_id,
        creator_user_id=user.id,
        title=payload.title,
        description=payload.description,
    )
    session.add(challenge)
    session.commit()
    session.refresh(challenge)
    return challenge


@router.get("")
def list_challenges(session: SessionDep, _: CurrentUser) -> list[Challenge]:
    """Каталог всех челленджей по заголовку — их можно найти и присоединиться."""
    return session.exec(select(Challenge).order_by(Challenge.title)).all()


@router.post("/{challenge_id}/join", status_code=status.HTTP_201_CREATED)
def join_challenge(
    challenge_id: int, session: SessionDep, user: CurrentUser
) -> ChallengeParticipant:
    """Присоединиться к челленджу. 404 — нет челленджа; 409 — уже участвую."""
    if session.get(Challenge, challenge_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Челлендж не найден")
    participant = ChallengeParticipant(challenge_id=challenge_id, user_id=user.id)
    session.add(participant)
    try:
        session.commit()
    except IntegrityError as exc:
        # unique (challenge_id, user_id): повторный join упирается сюда, а не плодит дубль.
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Вы уже участвуете в челлендже"
        ) from exc
    session.refresh(participant)
    return participant


@router.post("/{challenge_id}/proofs", status_code=status.HTTP_201_CREATED)
async def upload_challenge_proof(
    challenge_id: int,
    session: SessionDep,
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
    notes: Annotated[str | None, Form()] = None,
) -> ChallengeProof:
    """Загрузить видео-пруф участия. 404 — нет челленджа/не участвую; 422 — пустой/битый файл.

    Видео + ffmpeg-превью пишет общий video_proof (байты в БД не хранятся); при сбое
    ffmpeg запись в БД не появляется (файл откатывается), а наружу уходит 422.
    """
    participant = _my_participation_or_404(session, challenge_id, user.id)
    video_bytes = await file.read()
    if not video_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Пустой файл видео"
        )
    try:
        return proof_service.save_proof(
            session, participant.id, video_bytes, filename=file.filename, notes=notes
        )
    except proof_service.ThumbnailError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Не удалось сгенерировать превью из видео: {exc}",
        ) from exc


@router.patch("/{challenge_id}/participation")
def update_participation_status(
    challenge_id: int,
    payload: ParticipationUpdate,
    session: SessionDep,
    user: CurrentUser,
) -> ChallengeParticipant:
    """Сменить статус участия. 404 — нет челленджа/не участвую; 409 — недопустимый переход.

    Переход в completed («verify») требует хотя бы один видео-пруф, иначе 409 — статус
    не меняется. Недопустимый переход (см. _ALLOWED_TRANSITIONS) тоже 409.
    """
    participant = _my_participation_or_404(session, challenge_id, user.id)
    current = ChallengeParticipantStatus(participant.status)
    target = payload.status
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Недопустимый переход статуса: {current.value} → {target.value}",
        )
    if target is ChallengeParticipantStatus.completed and not proof_service.has_proof(
        session, participant.id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Нельзя завершить челлендж без видео-пруфа",
        )
    participant.status = target.value
    session.add(participant)
    session.commit()
    session.refresh(participant)
    return participant
