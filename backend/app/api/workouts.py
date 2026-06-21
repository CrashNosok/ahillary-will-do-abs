"""Логирование силовой тренировки (S3.4): создать сессию с подходами + чтение.

Одна силовая тренировка = workout_session + её strength_set'ы (подходы). POST /workouts
создаёт сессию и все подходы за один запрос (≥1 подход), пишет вес/повторы/отдых/RPE
и возвращает сессию с подходами. Каждый подход ссылается на упражнение (FK exercise_id);
несуществующее упражнение или вид спорта → 404 (SQLite не проверяет FK сам).
Все роуты под сессией (CurrentUser) — приложение однопользовательское.
"""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.models.sport import Exercise, Sport
from app.models.workout import StrengthSet, WorkoutSession

router = APIRouter(prefix="/workouts", tags=["workouts"])

SessionDep = Annotated[Session, Depends(get_session)]


class StrengthSetIn(BaseModel):
    exercise_id: int
    set_index: int | None = None
    weight_kg: float | None = None
    reps: int | None = None
    rest_sec: float | None = None  # отдых после подхода, сек
    rpe: float | None = None  # субъективная интенсивность (0–10)


class WorkoutCreate(BaseModel):
    date: dt.date
    sport_id: int | None = None
    title: str | None = None
    notes: str | None = None
    sets: list[StrengthSetIn] = Field(min_length=1)  # силовая сессия без подходов бессмысленна


class StrengthSetRead(BaseModel):
    id: int
    exercise_id: int
    set_index: int | None
    weight_kg: float | None
    reps: int | None
    rest_sec: float | None
    rpe: float | None


class WorkoutRead(BaseModel):
    id: int
    date: dt.date
    sport_id: int | None
    title: str | None
    notes: str | None
    created_at: dt.datetime
    sets: list[StrengthSetRead]


def _require_sport(session: Session, sport_id: int) -> None:
    if session.get(Sport, sport_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Вид спорта не найден")


def _require_exercises(session: Session, exercise_ids: set[int]) -> None:
    """Каждый подход должен ссылаться на существующее упражнение — иначе осиротевшая строка."""
    for exercise_id in exercise_ids:
        if session.get(Exercise, exercise_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Упражнение {exercise_id} не найдено",
            )


def _read(session: Session, ws: WorkoutSession) -> WorkoutRead:
    sets = session.exec(
        select(StrengthSet)
        .where(StrengthSet.session_id == ws.id)
        .order_by(StrengthSet.set_index, StrengthSet.id)
    ).all()
    return WorkoutRead(
        **ws.model_dump(),
        sets=[StrengthSetRead.model_validate(s.model_dump()) for s in sets],
    )


def _get_or_404(session: Session, workout_id: int) -> WorkoutSession:
    ws = session.get(WorkoutSession, workout_id)
    if ws is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тренировка не найдена")
    return ws


@router.post("", status_code=status.HTTP_201_CREATED)
def create_workout(payload: WorkoutCreate, session: SessionDep, _: CurrentUser) -> WorkoutRead:
    if payload.sport_id is not None:
        _require_sport(session, payload.sport_id)
    _require_exercises(session, {s.exercise_id for s in payload.sets})

    ws = WorkoutSession(
        date=payload.date, sport_id=payload.sport_id, title=payload.title, notes=payload.notes
    )
    session.add(ws)
    session.commit()
    session.refresh(ws)

    for item in payload.sets:
        session.add(StrengthSet(session_id=ws.id, **item.model_dump()))
    session.commit()

    return _read(session, ws)


@router.get("")
def list_workouts(session: SessionDep, _: CurrentUser) -> list[WorkoutRead]:
    sessions = session.exec(
        select(WorkoutSession).order_by(WorkoutSession.date.desc(), WorkoutSession.id.desc())
    ).all()
    return [_read(session, ws) for ws in sessions]


@router.get("/{workout_id}")
def get_workout(workout_id: int, session: SessionDep, _: CurrentUser) -> WorkoutRead:
    return _read(session, _get_or_404(session, workout_id))
