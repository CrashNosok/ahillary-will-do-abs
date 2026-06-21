"""Progress API (S2.4): временные ряды для графиков тела.

GET /progress/body?start&end — ряды по датам за выбранный период:
- weight_kg — вес из inbody_measurement (точки только там, где вес заполнен);
- circumferences — обхваты из body_measurement, по одному ряду на метрику.

Период по умолчанию — последние ~6 месяцев (замеры редкие, ~раз в 2 недели).
start > end → 422. Роут под сессией (CurrentUser) — приложение однопользовательское.
"""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.models.body import BodyMeasurement, InbodyMeasurement

router = APIRouter(prefix="/progress", tags=["progress"])

SessionDep = Annotated[Session, Depends(get_session)]

DEFAULT_RANGE_DAYS = 180

# Обхваты body_measurement для графиков (height/notes — не ряды прогресса).
CIRCUMFERENCE_FIELDS = (
    "waist_cm",
    "belly_cm",
    "calf_l_cm",
    "calf_r_cm",
    "chest_cm",
    "shoulders_cm",
    "biceps_l_cm",
    "biceps_r_cm",
    "glutes_cm",
)


class SeriesPoint(BaseModel):
    date: dt.date
    value: float


class BodyProgressOut(BaseModel):
    start: dt.date
    end: dt.date
    weight_kg: list[SeriesPoint]
    circumferences: dict[str, list[SeriesPoint]]


@router.get("/body")
def get_body_progress(
    session: SessionDep,
    _: CurrentUser,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> BodyProgressOut:
    end = end or dt.date.today()
    start = start or end - dt.timedelta(days=DEFAULT_RANGE_DAYS - 1)
    if start > end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Начало диапазона позже конца",
        )

    inbody = session.exec(
        select(InbodyMeasurement)
        .where(InbodyMeasurement.date >= start, InbodyMeasurement.date <= end)
        .order_by(InbodyMeasurement.date, InbodyMeasurement.id)
    ).all()
    weight = [
        SeriesPoint(date=m.date, value=m.weight_kg) for m in inbody if m.weight_kg is not None
    ]

    body = session.exec(
        select(BodyMeasurement)
        .where(BodyMeasurement.date >= start, BodyMeasurement.date <= end)
        .order_by(BodyMeasurement.date, BodyMeasurement.id)
    ).all()
    circumferences = {
        field: [
            SeriesPoint(date=m.date, value=getattr(m, field))
            for m in body
            if getattr(m, field) is not None
        ]
        for field in CIRCUMFERENCE_FIELDS
    }

    return BodyProgressOut(start=start, end=end, weight_kg=weight, circumferences=circumferences)
