"""Челленджи (M6·B34): создание/список + участие (join).

POST /challenges — завести вызов; creator_user_id берётся из сессии (а не из тела).
GET /challenges — каталог всех челленджей (их находят и присоединяются), по заголовку.
POST /challenges/{id}/join — стать участником: создаёт challenge_participant(user_id=me).
Все роуты под сессией (CurrentUser). is_base не выставляется пользователем — базовые
(встроенные) челленджи заводятся отдельно; обычное создание даёт пользовательский (False).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.models.challenge import Challenge, ChallengeParticipant
from app.models.sport import Sport

router = APIRouter(prefix="/challenges", tags=["challenges"])

SessionDep = Annotated[Session, Depends(get_session)]


class ChallengeCreate(BaseModel):
    sport_id: int
    title: str
    description: str


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
