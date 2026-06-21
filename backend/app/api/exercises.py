"""CRUD упражнений библиотеки (S3.2).

У каждого вида спорта своя библиотека упражнений: exercise(sport_id, name, unit, notes).
sport_id обязателен и должен ссылаться на существующий вид спорта (иначе 404 — SQLite
не проверяет FK сам). Список можно отфильтровать по виду спорта: GET /exercises?sport_id=.
Все роуты под сессией (CurrentUser) — приложение однопользовательское.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.models.sport import Exercise, Sport

router = APIRouter(prefix="/exercises", tags=["exercises"])

SessionDep = Annotated[Session, Depends(get_session)]


class ExerciseCreate(BaseModel):
    sport_id: int
    name: str
    unit: str | None = None
    notes: str | None = None


class ExerciseUpdate(BaseModel):
    name: str | None = None
    unit: str | None = None
    notes: str | None = None


def _get_or_404(session: Session, exercise_id: int) -> Exercise:
    exercise = session.get(Exercise, exercise_id)
    if exercise is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Упражнение не найдено")
    return exercise


def _require_sport(session: Session, sport_id: int) -> None:
    """Упражнение нельзя привязать к несуществующему виду спорта — 404 вместо осиротевшей строки."""
    if session.get(Sport, sport_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Вид спорта не найден")


@router.post("", status_code=status.HTTP_201_CREATED)
def create_exercise(payload: ExerciseCreate, session: SessionDep, _: CurrentUser) -> Exercise:
    _require_sport(session, payload.sport_id)
    exercise = Exercise(**payload.model_dump())
    session.add(exercise)
    session.commit()
    session.refresh(exercise)
    return exercise


@router.get("")
def list_exercises(
    session: SessionDep, _: CurrentUser, sport_id: int | None = None
) -> list[Exercise]:
    query = select(Exercise)
    if sport_id is not None:
        query = query.where(Exercise.sport_id == sport_id)
    return session.exec(query.order_by(Exercise.name)).all()


@router.get("/{exercise_id}")
def get_exercise(exercise_id: int, session: SessionDep, _: CurrentUser) -> Exercise:
    return _get_or_404(session, exercise_id)


@router.patch("/{exercise_id}")
def update_exercise(
    exercise_id: int, payload: ExerciseUpdate, session: SessionDep, _: CurrentUser
) -> Exercise:
    exercise = _get_or_404(session, exercise_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(exercise, key, value)
    session.add(exercise)
    session.commit()
    session.refresh(exercise)
    return exercise


@router.delete("/{exercise_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_exercise(exercise_id: int, session: SessionDep, _: CurrentUser) -> None:
    exercise = _get_or_404(session, exercise_id)
    session.delete(exercise)
    session.commit()
