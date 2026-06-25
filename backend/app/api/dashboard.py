"""Дашборд: флаги данных по дням (хитмап) + текущий стрик логирования (S1.13).

GET /dashboard?start&end — по каждому дню диапазона флаги has_food/has_activity/
has_training/has_measurement и общий current_streak (серия «еда+активность» на сегодня).
По умолчанию диапазон — последние 30 дней. start > end → 422.
Роут под сессией (CurrentUser) — приложение однопользовательское.
"""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.services import dashboard

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

SessionDep = Annotated[Session, Depends(get_session)]

DEFAULT_RANGE_DAYS = 30


class DayFlags(BaseModel):
    date: dt.date
    has_food: bool
    has_activity: bool
    has_training: bool
    has_measurement: bool
    has_weight: bool
    has_body: bool
    has_photo: bool
    has_surpassed_self: bool
    has_workout_media: bool
    has_full_measurements: bool


class TodaySummary(BaseModel):
    date: dt.date
    kcal_in: int
    kcal_out: int
    deficit: int


class DashboardOut(BaseModel):
    start: dt.date
    end: dt.date
    days: list[DayFlags]
    current_streak: int
    today: TodaySummary


@router.get("")
def get_dashboard(
    session: SessionDep,
    user: CurrentUser,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> DashboardOut:
    end = end or dt.date.today()
    start = start or end - dt.timedelta(days=DEFAULT_RANGE_DAYS - 1)
    try:
        flags = dashboard.day_flags(start, end, session, user_id=user.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return DashboardOut(
        start=start,
        end=end,
        days=[DayFlags(**vars(f)) for f in flags],
        current_streak=dashboard.current_streak(session, user_id=user.id),
        today=TodaySummary(**vars(dashboard.today_summary(session, user_id=user.id))),
    )
