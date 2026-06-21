"""CRUD виды спорта (S3.1).

Пользователь заводит дисциплины: sport(name, type, description). type валидируется
схемой запроса (strength/cardio/skill → иначе 422). name уникален — повтор отдаёт 409.
Все роуты под сессией (CurrentUser) — приложение однопользовательское.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.models.sport import Sport, SportType

router = APIRouter(prefix="/sports", tags=["sports"])

SessionDep = Annotated[Session, Depends(get_session)]


class SportCreate(BaseModel):
    name: str
    type: SportType
    description: str | None = None


class SportUpdate(BaseModel):
    name: str | None = None
    type: SportType | None = None
    description: str | None = None


def _get_or_404(session: Session, sport_id: int) -> Sport:
    sport = session.get(Sport, sport_id)
    if sport is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Вид спорта не найден")
    return sport


def _commit_unique(session: Session, sport: Sport) -> Sport:
    """Сохраняет и переводит конфликт уникального name в 409 вместо 500."""
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Вид спорта с таким именем уже есть"
        ) from exc
    session.refresh(sport)
    return sport


@router.post("", status_code=status.HTTP_201_CREATED)
def create_sport(payload: SportCreate, session: SessionDep, _: CurrentUser) -> Sport:
    sport = Sport(**payload.model_dump())
    session.add(sport)
    return _commit_unique(session, sport)


@router.get("")
def list_sports(session: SessionDep, _: CurrentUser) -> list[Sport]:
    return session.exec(select(Sport).order_by(Sport.name)).all()


@router.get("/{sport_id}")
def get_sport(sport_id: int, session: SessionDep, _: CurrentUser) -> Sport:
    return _get_or_404(session, sport_id)


@router.patch("/{sport_id}")
def update_sport(sport_id: int, payload: SportUpdate, session: SessionDep, _: CurrentUser) -> Sport:
    sport = _get_or_404(session, sport_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(sport, key, value)
    session.add(sport)
    return _commit_unique(session, sport)


@router.delete("/{sport_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sport(sport_id: int, session: SessionDep, _: CurrentUser) -> None:
    sport = _get_or_404(session, sport_id)
    session.delete(sport)
    session.commit()
