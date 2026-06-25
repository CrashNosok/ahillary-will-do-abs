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
from app.models.body import BodyMeasurement, InbodyMeasurement, ProgressPhoto
from app.models.nutrition import FoodEntry
from app.models.workout import WorkoutMedia, WorkoutSession


@dataclass(frozen=True)
class DayFlag:
    """Флаги наличия данных за один день (для ячейки хитмапа).

    Ежедневные категории (дневной «стакан»): food/activity/training.
    Недельные (наливаются в «общую чашу» недели): weight/body/photo.
    has_measurement (body|inbody) оставлен для легаси-потребителей (Заряд дня).

    Новые сигналы (M4·B20), все по дню и со скоупом по user_id:
    - has_surpassed_self — в этот день есть тренировка с отметкой личного рекорда;
    - has_workout_media — к тренировке этого дня прикреплено хотя бы одно медиа;
    - has_full_measurements — за день залогированы ОБА вида замеров (обхваты body И вес/InBody).
    """

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
    # Заполненные дневные категории в порядке появления (по времени первого ввода за день):
    # ['has_training', 'has_food', ...]. Фронт заливает «жидкость» дня в этом порядке (снизу-вверх).
    daily_order: tuple[str, ...]


@dataclass(frozen=True)
class TodaySummary:
    """Энергобаланс за сегодня для сводки дашборда (S1.15)."""

    date: dt.date
    kcal_in: int  # сумма kcal съеденного за день
    kcal_out: int  # total_kcal активности (0, если дня активности нет)
    deficit: int  # kcal_out − kcal_in: >0 — дефицит, <0 — профицит


def _dates(
    session: Session,
    date_col,
    user_id_col,
    user_id: int,
    start: dt.date,
    end: dt.date,
    *extra,
) -> set[dt.date]:
    """Множество дат владельца в [start; end], где в таблице есть запись.

    Скоуп по user_id — дашборд показывает данные только залогиненного пользователя.
    `extra` — дополнительные условия фильтра (напр. отметка «превзошёл себя»).
    """
    stmt = (
        select(date_col)
        .where(date_col >= start, date_col <= end, user_id_col == user_id, *extra)
        .distinct()
    )
    return {d for d in session.exec(stmt).all() if d is not None}


def _first_ts_by_date(
    session: Session, date_col, ts_col, user_id_col, user_id: int, start: dt.date, end: dt.date
) -> dict[dt.date, dt.datetime]:
    """date → самое раннее время записи владельца за день (min ts). Для порядка категорий дня."""
    stmt = (
        select(date_col, func.min(ts_col))
        .where(date_col >= start, date_col <= end, user_id_col == user_id)
        .group_by(date_col)
    )
    return {d: ts for d, ts in session.exec(stmt).all() if d is not None and ts is not None}


def day_flags(start: dt.date, end: dt.date, session: Session, *, user_id: int) -> list[DayFlag]:
    """Флаги по каждому дню диапазона включительно для user_id. start > end → ValueError."""
    if start > end:
        raise ValueError("Начало диапазона позже конца")

    food = _dates(session, FoodEntry.date, FoodEntry.user_id, user_id, start, end)
    activity = _dates(session, ActivityDay.date, ActivityDay.user_id, user_id, start, end)
    training = _dates(session, WorkoutSession.date, WorkoutSession.user_id, user_id, start, end)
    weight = _dates(  # вес/InBody
        session, InbodyMeasurement.date, InbodyMeasurement.user_id, user_id, start, end
    )
    body = _dates(  # обхваты-«замеры»
        session, BodyMeasurement.date, BodyMeasurement.user_id, user_id, start, end
    )
    photo = _dates(session, ProgressPhoto.date, ProgressPhoto.user_id, user_id, start, end)
    measurement = body | weight  # легаси-флаг (Заряд дня)
    # M4·B20 — новые сигналы дня (скоуп по user_id):
    surpassed = _dates(  # дни с тренировкой-личным-рекордом
        session,
        WorkoutSession.date,
        WorkoutSession.user_id,
        user_id,
        start,
        end,
        WorkoutSession.surpassed_self.is_(True),
    )
    workout_media = _workout_media_dates(session, user_id, start, end)
    full_measurements = body & weight  # «полный» замер дня = обхваты И вес одновременно

    # Время первого ввода каждой дневной категории за день — для порядка заливки (еда: created_at,
    # активность: parsed_at, тренировка: created_at).
    food_ts = _first_ts_by_date(
        session, FoodEntry.date, FoodEntry.created_at, FoodEntry.user_id, user_id, start, end
    )
    activity_ts = _first_ts_by_date(
        session, ActivityDay.date, ActivityDay.parsed_at, ActivityDay.user_id, user_id, start, end
    )
    training_ts = _first_ts_by_date(
        session,
        WorkoutSession.date,
        WorkoutSession.created_at,
        WorkoutSession.user_id,
        user_id,
        start,
        end,
    )

    def _daily_order(day: dt.date) -> tuple[str, ...]:
        present = []
        if day in food:
            present.append(("has_food", food_ts.get(day)))
        if day in activity:
            present.append(("has_activity", activity_ts.get(day)))
        if day in training:
            present.append(("has_training", training_ts.get(day)))
        present.sort(key=lambda kt: (kt[1] is None, kt[1]))  # по времени; None — в конец
        return tuple(key for key, _ in present)

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
                has_weight=day in weight,
                has_body=day in body,
                has_photo=day in photo,
                has_surpassed_self=day in surpassed,
                has_workout_media=day in workout_media,
                has_full_measurements=day in full_measurements,
                daily_order=_daily_order(day),
            )
        )
        day += dt.timedelta(days=1)
    return days


def _workout_media_dates(
    session: Session, user_id: int, start: dt.date, end: dt.date
) -> set[dt.date]:
    """Даты владельца в [start; end], где у тренировки есть хотя бы одно медиа.

    WorkoutMedia не хранит ни даты, ни user_id — берём их у родительской сессии
    (join по session_id). Скоуп по WorkoutSession.user_id.
    """
    stmt = (
        select(WorkoutSession.date)
        .join(WorkoutMedia, WorkoutMedia.session_id == WorkoutSession.id)
        .where(
            WorkoutSession.date >= start,
            WorkoutSession.date <= end,
            WorkoutSession.user_id == user_id,
        )
        .distinct()
    )
    return {d for d in session.exec(stmt).all() if d is not None}


def current_streak(session: Session, *, user_id: int, today: dt.date | None = None) -> int:
    """Серия последовательных полных дней (еда+активность) владельца, кончающаяся сегодня.

    Грейс на незакрытый день: если сегодня ещё не полный, отсчёт ведём от вчера.
    Множество полных дней конечно, поэтому обход назад сам останавливается на разрыве.
    """
    today = today or dt.date.today()
    complete = _dates(
        session, FoodEntry.date, FoodEntry.user_id, user_id, dt.date.min, today
    ) & _dates(session, ActivityDay.date, ActivityDay.user_id, user_id, dt.date.min, today)

    day = today if today in complete else today - dt.timedelta(days=1)
    streak = 0
    while day in complete:
        streak += 1
        day -= dt.timedelta(days=1)
    return streak


def today_summary(session: Session, *, user_id: int, today: dt.date | None = None) -> TodaySummary:
    """Сводка владельца за сегодня: ккал съедено (food) и потрачено (activity.total_kcal).

    kcal_in — сумма kcal всех записей еды за день; kcal_out — total_kcal дня
    активности (0, если его нет). deficit = kcal_out − kcal_in.
    """
    today = today or dt.date.today()
    kcal_in = session.exec(
        select(func.coalesce(func.sum(FoodEntry.kcal), 0.0)).where(
            FoodEntry.date == today, FoodEntry.user_id == user_id
        )
    ).one()
    # activity_day с составным PK (user_id, date) — берём день владельца запросом по ключу.
    activity = session.exec(
        select(ActivityDay).where(ActivityDay.date == today, ActivityDay.user_id == user_id)
    ).first()
    kcal_out = activity.total_kcal if activity and activity.total_kcal is not None else 0
    kcal_in = round(kcal_in)
    return TodaySummary(date=today, kcal_in=kcal_in, kcal_out=kcal_out, deficit=kcal_out - kcal_in)
