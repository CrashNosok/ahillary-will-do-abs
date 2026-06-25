"""CRUD SMART-цели (S1.3).

Сквозная сущность цели: создать / прочитать / обновить / архивировать. Инвариант
карточки — активной считается ровно одна цель (status == "active"): при создании
новой активной цели или переводе цели в active прочие активные архивируются.
GET /goals/active всегда отдаёт текущую активную цель (404, если её нет).
Все роуты под сессией (CurrentUser) — приложение однопользовательское.
"""

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.models.goal import GoalStatus, SmartGoal

router = APIRouter(prefix="/goals", tags=["goals"])

SessionDep = Annotated[Session, Depends(get_session)]


class GoalCreate(BaseModel):
    target_weight_kg: float | None = None
    target_body_fat_pct: float | None = None
    target_measurements_json: dict[str, Any] | None = None
    start_date: dt.date | None = None
    deadline: dt.date | None = None
    baseline_json: dict[str, Any] | None = None
    why_notes: str | None = None
    status: GoalStatus = GoalStatus.active


class GoalUpdate(BaseModel):
    target_weight_kg: float | None = None
    target_body_fat_pct: float | None = None
    target_measurements_json: dict[str, Any] | None = None
    start_date: dt.date | None = None
    deadline: dt.date | None = None
    baseline_json: dict[str, Any] | None = None
    why_notes: str | None = None
    status: GoalStatus | None = None


def _archive_other_active(session: Session, keep_id: int | None) -> None:
    """Инвариант «одна активная»: архивируем все active-цели, кроме keep_id."""
    actives = session.exec(select(SmartGoal).where(SmartGoal.status == GoalStatus.active)).all()
    for goal in actives:
        if goal.id != keep_id:
            goal.status = GoalStatus.archived
            session.add(goal)


def _get_or_404(session: Session, goal_id: int) -> SmartGoal:
    goal = session.get(SmartGoal, goal_id)
    if goal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Цель не найдена")
    return goal


@router.post("", status_code=status.HTTP_201_CREATED)
def create_goal(payload: GoalCreate, session: SessionDep, user: CurrentUser) -> SmartGoal:
    goal = SmartGoal(**payload.model_dump(), user_id=user.id)
    session.add(goal)
    session.flush()  # присвоить goal.id до архивации прочих активных
    if goal.status == GoalStatus.active:
        _archive_other_active(session, keep_id=goal.id)
    session.commit()
    session.refresh(goal)
    return goal


@router.get("")
def list_goals(session: SessionDep, _: CurrentUser) -> list[SmartGoal]:
    stmt = select(SmartGoal).order_by(SmartGoal.created_at.desc(), SmartGoal.id.desc())
    return session.exec(stmt).all()


@router.get("/active")
def get_active_goal(session: SessionDep, _: CurrentUser) -> SmartGoal:
    goal = session.exec(select(SmartGoal).where(SmartGoal.status == GoalStatus.active)).first()
    if goal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Активной цели нет")
    return goal


@router.get("/{goal_id}")
def get_goal(goal_id: int, session: SessionDep, _: CurrentUser) -> SmartGoal:
    return _get_or_404(session, goal_id)


@router.patch("/{goal_id}")
def update_goal(
    goal_id: int, payload: GoalUpdate, session: SessionDep, _: CurrentUser
) -> SmartGoal:
    goal = _get_or_404(session, goal_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(goal, key, value)
    session.add(goal)
    if goal.status == GoalStatus.active:
        _archive_other_active(session, keep_id=goal.id)
    session.commit()
    session.refresh(goal)
    return goal


@router.post("/{goal_id}/archive")
def archive_goal(goal_id: int, session: SessionDep, _: CurrentUser) -> SmartGoal:
    goal = _get_or_404(session, goal_id)
    goal.status = GoalStatus.archived
    session.add(goal)
    session.commit()
    session.refresh(goal)
    return goal
