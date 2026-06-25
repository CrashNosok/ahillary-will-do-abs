"""Дисциплины пользователя (M2·B19): /me/sports — список + link/unlink.

Пользователь привязывает к себе виды спорта из каталога (sport) через таблицу-связку
user_sport. Все роуты под сессией (CurrentUser) и скоупятся по user.id — чужие связки
не видны и не трогаются. Каталог sport общий, а факт «веду эту дисциплину» — личный.
"""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.models.sport import Sport, SportCategory
from app.models.user_sport import UserSport

router = APIRouter(prefix="/me/sports", tags=["me"])

SessionDep = Annotated[Session, Depends(get_session)]


class UserSportLink(BaseModel):
    """Тело link: какую дисциплину привязать (+ опц. текущий уровень и рейтинг)."""

    sport_id: int
    current_level_id: int | None = None
    rating: float | None = None


class UserSportRead(BaseModel):
    """Связка для UI: атрибуты user_sport + name/category/description из каталога sport."""

    sport_id: int
    name: str
    category: SportCategory
    description: str | None
    current_level_id: int | None
    rating: float | None
    joined_at: dt.datetime


def _to_read(link: UserSport, sport: Sport) -> UserSportRead:
    """Собирает ответ из связки и её каталожной дисциплины (общий код list и link)."""
    return UserSportRead(
        sport_id=link.sport_id,
        name=sport.name,
        category=sport.category,
        description=sport.description,
        current_level_id=link.current_level_id,
        rating=link.rating,
        joined_at=link.joined_at,
    )


@router.get("")
def list_my_sports(session: SessionDep, user: CurrentUser) -> list[UserSportRead]:
    """Дисциплины текущего пользователя со связкой и данными каталога, по имени спорта.

    JOIN user_sport↔sport одним запросом (без N+1). Скоуп по user.id — только свои связки.
    """
    rows = session.exec(
        select(UserSport, Sport)
        .join(Sport, UserSport.sport_id == Sport.id)
        .where(UserSport.user_id == user.id)
        .order_by(Sport.name)
    ).all()
    return [_to_read(link, sport) for link, sport in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
def link_sport(payload: UserSportLink, session: SessionDep, user: CurrentUser) -> UserSportRead:
    """Привязать дисциплину к пользователю. 404 — нет такого sport; 409 — уже привязана."""
    sport = session.get(Sport, payload.sport_id)
    if sport is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Вид спорта не найден")
    if session.get(UserSport, (user.id, payload.sport_id)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Дисциплина уже привязана")
    link = UserSport(
        user_id=user.id,
        sport_id=payload.sport_id,
        current_level_id=payload.current_level_id,
        rating=payload.rating,
    )
    session.add(link)
    try:
        session.commit()
    except IntegrityError as exc:
        # Подстраховка к pre-check выше: гонка двух link той же пары упрётся в составной PK.
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Дисциплина уже привязана"
        ) from exc
    session.refresh(link)
    return _to_read(link, sport)


@router.delete("/{sport_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_sport(sport_id: int, session: SessionDep, user: CurrentUser) -> None:
    """Отвязать дисциплину от пользователя. 404, если связки нет (в т.ч. чужая)."""
    link = session.get(UserSport, (user.id, sport_id))
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Дисциплина не привязана")
    session.delete(link)
    session.commit()
