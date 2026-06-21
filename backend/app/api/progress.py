"""Progress API: временные ряды для графиков.

GET /progress/body?start&end (S2.4) — ряды тела за период:
- weight_kg — вес из inbody_measurement (точки только там, где вес заполнен);
- circumferences — обхваты из body_measurement, по одному ряду на метрику.

GET /progress/energy?start&end (S2.5) — ряды питания/энергии за период:
- kcal_in — съеденные ккал (сумма food_entry за день);
- kcal_out — потраченные ккал (activity_day.total_kcal);
- deficit — deficit_day.deficit_kcal (только полные дни — без ложного нуля);
- macros — тренд Б/Ж/У (суммы food_entry за день);
- steps / active_min — шаги и минуты активности из activity_day.

Общие правила: период фильтруется по [start; end]; точка ряда появляется только
там, где есть реальное (не-null) значение, поэтому пропуски дней не рвут ряд и не
дают ложных нулей. start > end → 422. Все роуты под сессией (CurrentUser) —
приложение однопользовательское.
"""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, select

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.models.activity import ActivityDay
from app.models.body import BodyMeasurement, InbodyMeasurement
from app.models.deficit import DeficitDay
from app.models.nutrition import FoodEntry

router = APIRouter(prefix="/progress", tags=["progress"])

SessionDep = Annotated[Session, Depends(get_session)]

DEFAULT_RANGE_DAYS = 180
# Энергия/питание — дневное разрешение, поэтому окно по умолчанию уже (квартал),
# а не полгода как у редких замеров тела.
DEFAULT_ENERGY_RANGE_DAYS = 90

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


MACRO_FIELDS = ("protein_g", "fat_g", "carb_g")


class EnergyProgressOut(BaseModel):
    start: dt.date
    end: dt.date
    kcal_in: list[SeriesPoint]
    kcal_out: list[SeriesPoint]
    deficit: list[SeriesPoint]
    macros: dict[str, list[SeriesPoint]]
    steps: list[SeriesPoint]
    active_min: list[SeriesPoint]


def _series(rows) -> list[SeriesPoint]:
    """Ряд из (date, value), пропуская дни без значения (value is None)."""
    return [SeriesPoint(date=d, value=v) for d, v in rows if v is not None]


def _round(value: float | None) -> float | None:
    """Округлить сумму до 1 знака (гасит float-шум); None пробрасываем как пропуск."""
    return None if value is None else round(value, 1)


@router.get("/energy")
def get_energy_progress(
    session: SessionDep,
    _: CurrentUser,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> EnergyProgressOut:
    end = end or dt.date.today()
    start = start or end - dt.timedelta(days=DEFAULT_ENERGY_RANGE_DAYS - 1)
    if start > end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Начало диапазона позже конца",
        )

    # Питание: суммы за день. SUM по дню = None, если все значения метрики null,
    # поэтому незаполненная метрика не даёт точку (без ложного нуля).
    food = session.exec(
        select(
            FoodEntry.date,
            func.sum(FoodEntry.kcal),
            func.sum(FoodEntry.protein_g),
            func.sum(FoodEntry.fat_g),
            func.sum(FoodEntry.carb_g),
        )
        .where(FoodEntry.date >= start, FoodEntry.date <= end)
        .group_by(FoodEntry.date)
        .order_by(FoodEntry.date)
    ).all()
    kcal_in = _series((d, _round(k)) for d, k, *_ in food)
    macros = {
        field: _series((row[0], _round(row[i + 2])) for row in food)
        for i, field in enumerate(MACRO_FIELDS)
    }

    # Активность: kcal_out / шаги / минуты движения из дневного агрегата.
    activity = session.exec(
        select(ActivityDay.date, ActivityDay.total_kcal, ActivityDay.steps, ActivityDay.moving_min)
        .where(ActivityDay.date >= start, ActivityDay.date <= end)
        .order_by(ActivityDay.date)
    ).all()
    kcal_out = _series((d, total) for d, total, _, _ in activity)
    steps = _series((d, s) for d, _, s, _ in activity)
    active_min = _series((d, m) for d, _, _, m in activity)

    # Дефицит: только полные дни (deficit_kcal != None), неполные дни выпадают из ряда.
    deficit_rows = session.exec(
        select(DeficitDay.date, DeficitDay.deficit_kcal)
        .where(DeficitDay.date >= start, DeficitDay.date <= end)
        .order_by(DeficitDay.date)
    ).all()
    deficit = _series(deficit_rows)

    return EnergyProgressOut(
        start=start,
        end=end,
        kcal_in=kcal_in,
        kcal_out=kcal_out,
        deficit=deficit,
        macros=macros,
        steps=steps,
        active_min=active_min,
    )
