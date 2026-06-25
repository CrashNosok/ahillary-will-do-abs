"""CRUD виды спорта (S3.1).

Пользователь заводит дисциплины: sport(name, type, description). type валидируется
схемой запроса (strength/cardio/skill → иначе 422). name уникален — повтор отдаёт 409.
Все роуты под сессией (CurrentUser) — приложение однопользовательское.
"""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.models.achievement import Achievement, AchievementProof
from app.models.sport import Sport, SportType
from app.services import achievement as achievement_service
from app.services.achievement_schema import AthleteLevel, InvalidAchievementSetError
from app.services.llm import LLMError

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


class AchievementRead(BaseModel):
    """Ачивка для UI (S5.6): поля модели + has_proof — есть ли видео-пруф (рисовать превью)."""

    id: int
    sport_id: int | None
    title: str
    description: str | None
    level: str | None
    status: str
    created_at: dt.datetime
    unlocked_at: dt.datetime | None
    has_proof: bool


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


@router.get("/{sport_id}/achievements")
def list_sport_achievements(
    sport_id: int, session: SessionDep, _: CurrentUser
) -> list[AchievementRead]:
    """Ачивки вида спорта со статусами (locked/in_progress/unlocked), в порядке создания.

    Поле has_proof говорит UI, есть ли видео-пруф (рисовать ли превью в карточке, S5.6).
    404 для неизвестного спорта; пустой список — если набор ещё не сгенерирован.
    """
    _get_or_404(session, sport_id)
    achievements = session.exec(
        select(Achievement).where(Achievement.sport_id == sport_id).order_by(Achievement.id)
    ).all()
    # Одним запросом — id ачивок, у которых есть пруф (без N+1 по карточкам).
    proof_ids: set[int] = (
        set(
            session.exec(
                select(AchievementProof.achievement_id).where(
                    AchievementProof.achievement_id.in_([a.id for a in achievements])
                )
            ).all()
        )
        if achievements
        else set()
    )
    return [AchievementRead(**a.model_dump(), has_proof=a.id in proof_ids) for a in achievements]


@router.post("/{sport_id}/achievements/generate", status_code=status.HTTP_201_CREATED)
def generate_sport_achievements(
    sport_id: int,
    session: SessionDep,
    user: CurrentUser,
    level: Annotated[AthleteLevel, Query()] = AthleteLevel.beginner,
) -> list[Achievement]:
    """LLM-генератор ачивок (S5.1): тированный набор под дисциплину и уровень атлета.

    Уровень — query-параметр, по умолчанию самый безопасный (beginner). Ошибка модели или
    невалидный ответ после ретраев → 502 (сбой апстрима), в БД при этом ничего не пишется.
    """
    sport = _get_or_404(session, sport_id)
    try:
        return achievement_service.generate_achievements(session, sport, level, user_id=user.id)
    except (LLMError, InvalidAchievementSetError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Не удалось получить валидный набор ачивок от модели: {exc}",
        ) from exc
