"""Личные числовые цели по упражнениям: GET / upsert (PUT) / DELETE.

Цель — на пару (текущий пользователь, exercise_id); upsert по уникальному индексу, поэтому
повторная постановка обновляет значение, а не плодит дубли. Все роуты под сессией; цели
скоупятся по user_id (чужие не видны и не правятся). Несуществующее упражнение → 404.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.models.exercise_target import ExerciseTarget
from app.models.sport import Exercise

router = APIRouter(prefix="/exercise-targets", tags=["exercise-targets"])

SessionDep = Annotated[Session, Depends(get_session)]


class ExerciseTargetIn(BaseModel):
    exercise_id: int
    target_value: float
    unit: str | None = None


@router.get("")
def list_exercise_targets(
    session: SessionDep, user: CurrentUser, exercise_id: int | None = None
) -> list[ExerciseTarget]:
    """Цели владельца (опц. фильтр по exercise_id) — для целевых линий и формы кабинета."""
    query = select(ExerciseTarget).where(ExerciseTarget.user_id == user.id)
    if exercise_id is not None:
        query = query.where(ExerciseTarget.exercise_id == exercise_id)
    return session.exec(query.order_by(ExerciseTarget.exercise_id)).all()


@router.put("", status_code=status.HTTP_200_OK)
def upsert_exercise_target(
    payload: ExerciseTargetIn, session: SessionDep, user: CurrentUser
) -> ExerciseTarget:
    """Поставить/обновить цель упражнения (upsert по user_id+exercise_id). 404 — нет упражнения."""
    if session.get(Exercise, payload.exercise_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Упражнение не найдено")
    existing = session.exec(
        select(ExerciseTarget).where(
            ExerciseTarget.user_id == user.id,
            ExerciseTarget.exercise_id == payload.exercise_id,
        )
    ).first()
    target = existing or ExerciseTarget(user_id=user.id, exercise_id=payload.exercise_id)
    target.target_value = payload.target_value
    target.unit = payload.unit
    session.add(target)
    session.commit()
    session.refresh(target)
    return target


@router.delete("/{exercise_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_exercise_target(exercise_id: int, session: SessionDep, user: CurrentUser) -> None:
    """Снять цель по упражнению. Нет своей цели → 404 (чужую не раскрываем)."""
    target = session.exec(
        select(ExerciseTarget).where(
            ExerciseTarget.user_id == user.id, ExerciseTarget.exercise_id == exercise_id
        )
    ).first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Цель не найдена")
    session.delete(target)
    session.commit()
