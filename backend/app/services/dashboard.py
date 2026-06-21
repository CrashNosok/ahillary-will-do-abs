"""Данные дашборда: дневные флаги логирования (хитмап) и текущий стрик (S1.13).

day_flags — по каждому дню диапазона: была ли еда / активность / тренировка / замер.
Считаем пятью запросами «множеств дат» (а не запросом на день), затем собираем флаги.

current_streak — длина серии последовательных «полных» дней (еда И активность),
заканчивающейся сегодня. Грейс: если сегодня ещё не закрыт, серию меряем по вчера —
незавершённый текущий день не штрафуем. Разрыв (день без еды или без активности)
обрывает серию. Источник «есть», если за день существует хотя бы одна запись таблицы.
"""

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import func
from sqlmodel import Session, select

from app.models.activity import ActivityDay
from app.models.body import BodyMeasurement, InbodyMeasurement
from app.models.nutrition import FoodEntry
from app.models.workout import WorkoutSession


@dataclass(frozen=True)
class DayFlag:
    """Флаги наличия данных за один день (для ячейки хитмапа)."""

    date: dt.date
    has_food: bool
    has_activity: bool
    has_training: bool
    has_measurement: bool


@dataclass(frozen=True)
class TodaySummary:
    """Энергобаланс за сегодня для сводки дашборда (S1.15)."""

    date: dt.date
    kcal_in: int  # сумма kcal съеденного за день
    kcal_out: int  # total_kcal активности (0, если дня активности нет)
    deficit: int  # kcal_out − kcal_in: >0 — дефицит, <0 — профицит


def _dates(session: Session, column, start: dt.date, end: dt.date) -> set[dt.date]:
    """Множество дат в [start; end], по которым в таблице есть хотя бы одна запись."""
    stmt = select(column).where(column >= start, column <= end).distinct()
    return {d for d in session.exec(stmt).all() if d is not None}


def day_flags(start: dt.date, end: dt.date, session: Session) -> list[DayFlag]:
    """Флаги по каждому дню диапазона включительно. start > end → ValueError."""
    if start > end:
        raise ValueError("Начало диапазона позже конца")

    food = _dates(session, FoodEntry.date, start, end)
    activity = _dates(session, ActivityDay.date, start, end)
    training = _dates(session, WorkoutSession.date, start, end)
    measurement = _dates(session, BodyMeasurement.date, start, end) | _dates(
        session, InbodyMeasurement.date, start, end
    )

    days: list[DayFlag] = []
    day = start
    while day <= end:
        days.append(
            DayFlag(
                date=day,
                has_food=day in food,
                has_activity=day in activity,
                has_training=day in training,
                has_measurement=day in measurement,
            )
        )
        day += dt.timedelta(days=1)
    return days


def current_streak(session: Session, today: dt.date | None = None) -> int:
    """Серия последовательных полных дней (еда+активность), заканчивающаяся сегодня.

    Грейс на незакрытый день: если сегодня ещё не полный, отсчёт ведём от вчера.
    Множество полных дней конечно, поэтому обход назад сам останавливается на разрыве.
    """
    today = today or dt.date.today()
    complete = _dates(session, FoodEntry.date, dt.date.min, today) & _dates(
        session, ActivityDay.date, dt.date.min, today
    )

    day = today if today in complete else today - dt.timedelta(days=1)
    streak = 0
    while day in complete:
        streak += 1
        day -= dt.timedelta(days=1)
    return streak


def today_summary(session: Session, today: dt.date | None = None) -> TodaySummary:
    """Сводка за сегодня: ккал съедено (food) и потрачено (activity.total_kcal).

    kcal_in — сумма kcal всех записей еды за день; kcal_out — total_kcal дня
    активности (0, если его нет). deficit = kcal_out − kcal_in.
    """
    today = today or dt.date.today()
    kcal_in = session.exec(
        select(func.coalesce(func.sum(FoodEntry.kcal), 0.0)).where(FoodEntry.date == today)
    ).one()
    activity = session.get(ActivityDay, today)
    kcal_out = activity.total_kcal if activity and activity.total_kcal is not None else 0
    kcal_in = round(kcal_in)
    return TodaySummary(date=today, kcal_in=kcal_in, kcal_out=kcal_out, deficit=kcal_out - kcal_in)
