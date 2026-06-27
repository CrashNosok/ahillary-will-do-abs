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

GET /progress/goal (S2.6) — прогресс к активной SMART-цели по доступным метрикам:
- вес / %жира / обхваты — % к target_*, темп и грубый линейный прогноз (eta) к цели,
  флаг on_track (успеет ли eta к дедлайну). Метрики без измеримой колонки пропускаются.

GET /progress/strength?start&end (S3.11) — ряды силовых тренировок за период:
- by_exercise — на каждое упражнение: рабочий вес (макс за день), тренд 1ПМ (лучшая
  оценка Эпли за день), тоннаж (sum w*reps за день);
- by_group — тоннаж по виду спорта (группе упражнений) за день.

GET /progress/cardio?start&end (S3.11) — кардио-динамика во времени:
- by_exercise — на каждое упражнение: дистанция (км/день), темп (сек/км), средний
  пульс, пульсовая эффективность (метров на удар сердца). Точка появляется только
  там, где метрику можно посчитать (нет ложных нулей).

Общие правила: период фильтруется по [start; end]; точка ряда появляется только
там, где есть реальное (не-null) значение, поэтому пропуски дней не рвут ряд и не
дают ложных нулей. start > end → 422. Все роуты под сессией (CurrentUser) —
приложение однопользовательское.
"""

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, select

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.models.activity import ActivityDay
from app.models.body import BodyMeasurement, InbodyMeasurement
from app.models.deficit import DeficitDay
from app.models.goal import GoalStatus, SmartGoal
from app.models.nutrition import FoodEntry
from app.models.sport import Exercise
from app.models.workout import CardioLog, StrengthSet, WorkoutSession
from app.services.metrics import effective_targets, resolve_metric
from app.services.workout_metrics import epley_1rm

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
    user: CurrentUser,
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

    # Ряды считаем только по своим замерам (M0·B9).
    inbody = session.exec(
        select(InbodyMeasurement)
        .where(
            InbodyMeasurement.user_id == user.id,
            InbodyMeasurement.date >= start,
            InbodyMeasurement.date <= end,
        )
        .order_by(InbodyMeasurement.date, InbodyMeasurement.id)
    ).all()
    weight = [
        SeriesPoint(date=m.date, value=m.weight_kg) for m in inbody if m.weight_kg is not None
    ]

    body = session.exec(
        select(BodyMeasurement)
        .where(
            BodyMeasurement.user_id == user.id,
            BodyMeasurement.date >= start,
            BodyMeasurement.date <= end,
        )
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


# Состав тела из inbody_measurement для графиков динамики (S2.12). Вес отдаёт
# /progress/body, поэтому здесь — только четыре показателя состава.
INBODY_COMPOSITION_FIELDS = (
    "body_fat_pct",
    "muscle_mass_kg",
    "visceral_fat",
    "water",
)


class InbodyProgressOut(BaseModel):
    start: dt.date
    end: dt.date
    composition: dict[str, list[SeriesPoint]]


@router.get("/inbody")
def get_inbody_progress(
    session: SessionDep,
    user: CurrentUser,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> InbodyProgressOut:
    """Ряды состава тела (%жира, мыш.масса, висцеральный жир, вода) за период (S2.12).

    Источник — inbody_measurement; по одному ряду на показатель. Точка ряда есть
    только там, где значение не-null, поэтому редкие/неполные замеры не дают
    ложных нулей. start > end → 422.
    """
    end = end or dt.date.today()
    start = start or end - dt.timedelta(days=DEFAULT_RANGE_DAYS - 1)
    if start > end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Начало диапазона позже конца",
        )

    measurements = session.exec(
        select(InbodyMeasurement)
        .where(
            InbodyMeasurement.user_id == user.id,
            InbodyMeasurement.date >= start,
            InbodyMeasurement.date <= end,
        )
        .order_by(InbodyMeasurement.date, InbodyMeasurement.id)
    ).all()
    composition = {
        field: [
            SeriesPoint(date=m.date, value=getattr(m, field))
            for m in measurements
            if getattr(m, field) is not None
        ]
        for field in INBODY_COMPOSITION_FIELDS
    }

    return InbodyProgressOut(start=start, end=end, composition=composition)


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
    user: CurrentUser,
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
        .where(FoodEntry.user_id == user.id, FoodEntry.date >= start, FoodEntry.date <= end)
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
        .where(ActivityDay.user_id == user.id, ActivityDay.date >= start, ActivityDay.date <= end)
        .order_by(ActivityDay.date)
    ).all()
    kcal_out = _series((d, total) for d, total, _, _ in activity)
    steps = _series((d, s) for d, _, s, _ in activity)
    active_min = _series((d, m) for d, _, _, m in activity)

    # Дефицит: только полные дни (deficit_kcal != None), неполные дни выпадают из ряда.
    deficit_rows = session.exec(
        select(DeficitDay.date, DeficitDay.deficit_kcal)
        .where(DeficitDay.user_id == user.id, DeficitDay.date >= start, DeficitDay.date <= end)
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


# --- S2.6 Progress API: прогресс к SMART-цели --------------------------------


class GoalMetricProgress(BaseModel):
    metric: str  # имя поля измерения: weight_kg | body_fat_pct | waist_cm | …
    target: float
    baseline: float | None  # старт отсчёта: baseline_json@start_date или 1-й замер
    current: float | None  # последний замер
    remaining: float | None  # |target − current|, сколько ещё двигаться
    percent: float | None  # 0..100 прогресс baseline→target (None — нет данных)
    eta: dt.date | None  # грубый линейный прогноз достижения target
    on_track: bool | None  # eta ≤ deadline (None — нет eta/дедлайна)


class GoalProgressOut(BaseModel):
    goal_id: int
    start_date: dt.date | None
    deadline: dt.date | None
    metrics: list[GoalMetricProgress]


def _baseline_lookup(baseline_json: dict[str, Any] | None, *keys: str) -> float | None:
    """Значение базы из baseline_json по первому совпавшему ключу (число), иначе None."""
    if not baseline_json:
        return None
    for key in keys:
        value = baseline_json.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
    return None


def _dated_values(
    session: Session,
    model,
    col_name: str,
    start_date: dt.date | None,
    today: dt.date,
    user_id: int,
) -> list[tuple[dt.date, float]]:
    """Хронологический ряд (date, value) метрики из модели, пропуская null и будущее.

    Только свои замеры (M0·B9): model — BodyMeasurement/InbodyMeasurement, у обеих есть user_id.
    """
    column = getattr(model, col_name)
    conds = [model.user_id == user_id, column.is_not(None), model.date <= today]
    if start_date is not None:
        conds.append(model.date >= start_date)
    rows = session.exec(
        select(model.date, column).where(*conds).order_by(model.date, model.id)
    ).all()
    return [(d, float(v)) for d, v in rows]


def _percent(baseline: float | None, current: float | None, target: float) -> float | None:
    """Доля пути baseline→target, %; направление любое; 0..100. None — нет данных."""
    if baseline is None or current is None:
        return None
    denom = target - baseline
    if denom == 0:  # база уже равна цели — считаем достигнутой
        return 100.0
    pct = (current - baseline) / denom * 100
    return round(min(100.0, max(0.0, pct)), 1)


def _eta(
    baseline: float | None,
    baseline_date: dt.date | None,
    current: float | None,
    current_date: dt.date | None,
    target: float,
) -> dt.date | None:
    """Грубый линейный прогноз даты достижения target по темпу baseline→current."""
    if None in (baseline, baseline_date, current, current_date):
        return None
    span = (current_date - baseline_date).days
    if span <= 0:
        return None
    remaining = target - current
    if remaining == 0:  # уже на цели
        return current_date
    rate = (current - baseline) / span  # единиц в день
    if rate == 0 or (remaining > 0) != (rate > 0):  # стоим или движемся от цели
        return None
    return current_date + dt.timedelta(days=round(remaining / rate))


def _round1(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def _metric_progress(
    session: Session,
    goal: SmartGoal,
    today: dt.date,
    *,
    metric: str,
    target: float,
    model,
    col: str,
    baseline_keys: tuple[str, ...],
    user_id: int,
) -> GoalMetricProgress:
    points = _dated_values(session, model, col, goal.start_date, today, user_id)
    # baseline_json@start_date — синтетический самый ранний замер (точнее темп/процент),
    # но только если есть хотя бы один реальный замер и старт раньше него.
    bjson = _baseline_lookup(goal.baseline_json, *baseline_keys)
    if bjson is not None and goal.start_date is not None and points:
        if goal.start_date < points[0][0]:
            points = [(goal.start_date, bjson)] + points

    baseline = points[0][1] if points else None
    baseline_date = points[0][0] if points else None
    current = points[-1][1] if points else None
    current_date = points[-1][0] if points else None

    percent = _percent(baseline, current, target)
    eta = _eta(baseline, baseline_date, current, current_date, target)
    remaining = None if current is None else round(abs(target - current), 1)
    on_track = (eta <= goal.deadline) if (eta is not None and goal.deadline is not None) else None

    return GoalMetricProgress(
        metric=metric,
        target=round(float(target), 1),
        baseline=_round1(baseline),
        current=_round1(current),
        remaining=remaining,
        percent=percent,
        eta=eta,
        on_track=on_track,
    )


@router.get("/goal")
def get_goal_progress(session: SessionDep, user: CurrentUser) -> GoalProgressOut:
    # Активная цель СТРОГО владельца (M0·B5): SmartGoal владельческая, иначе прогресс
    # считался бы по чужой цели против своих замеров (межаккаунтная утечка).
    # order_by(id) — детерминизм, если активных целей вдруг больше одной.
    goal = session.exec(
        select(SmartGoal)
        .where(SmartGoal.status == GoalStatus.active, SmartGoal.user_id == user.id)
        .order_by(SmartGoal.id)
    ).first()
    if goal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Активной цели нет")

    today = dt.date.today()
    metrics: list[GoalMetricProgress] = []

    # Единая карта целей по реестру метрик (с фолбэком на легаси-поля). eta/on_track имеют
    # смысл только для метрик тела (есть траектория замеров) — дневные нормы (model=None)
    # пропускаем: их цели отдаются через объект цели и снапшот, а не через этот эндпоинт.
    for key, target in effective_targets(goal).items():
        spec = resolve_metric(key)
        if spec is None or spec.model is None:
            continue
        metrics.append(
            _metric_progress(
                session,
                goal,
                today,
                metric=spec.key,
                target=target,
                model=spec.model,
                col=spec.column,
                baseline_keys=(spec.key,),
                user_id=user.id,
            )
        )

    return GoalProgressOut(
        goal_id=goal.id,
        start_date=goal.start_date,
        deadline=goal.deadline,
        metrics=metrics,
    )


# --- S3.11 Training progress API: ряды силовой и кардио ----------------------


def _resolve_range(start: dt.date | None, end: dt.date | None) -> tuple[dt.date, dt.date]:
    """Окно [start; end] с дефолтом DEFAULT_RANGE_DAYS; start > end → 422."""
    end = end or dt.date.today()
    start = start or end - dt.timedelta(days=DEFAULT_RANGE_DAYS - 1)
    if start > end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Начало диапазона позже конца",
        )
    return start, end


def _points(by_date: dict[dt.date, float], ndigits: int = 2) -> list[SeriesPoint]:
    """{дата: значение} → хронологический ряд точек (округление гасит float-шум)."""
    return [SeriesPoint(date=d, value=round(v, ndigits)) for d, v in sorted(by_date.items())]


class ExerciseStrengthSeries(BaseModel):
    exercise_id: int
    working_weight: list[SeriesPoint]  # макс рабочий вес за день
    best_1rm: list[SeriesPoint]  # лучшая оценка 1ПМ (Эпли) за день
    tonnage: list[SeriesPoint]  # тоннаж (sum w*reps) за день


class GroupTonnageSeries(BaseModel):
    sport_id: int | None  # вид спорта = группа упражнений; None — упражнение без спорта
    tonnage: list[SeriesPoint]


class StrengthProgressOut(BaseModel):
    start: dt.date
    end: dt.date
    by_exercise: list[ExerciseStrengthSeries]
    by_group: list[GroupTonnageSeries]


@router.get("/strength")
def get_strength_progress(
    session: SessionDep,
    user: CurrentUser,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> StrengthProgressOut:
    start, end = _resolve_range(start, end)

    # Подходы за период с датой сессии и видом спорта упражнения. Outer join по
    # упражнению — подход с удалённым упражнением не теряется (sport_id = None).
    rows = session.exec(
        select(
            WorkoutSession.date,
            StrengthSet.exercise_id,
            Exercise.sport_id,
            StrengthSet.weight_kg,
            StrengthSet.reps,
        )
        .select_from(StrengthSet)
        .join(WorkoutSession, StrengthSet.session_id == WorkoutSession.id)
        .join(Exercise, StrengthSet.exercise_id == Exercise.id, isouter=True)
        .where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.date >= start,
            WorkoutSession.date <= end,
        )
        .order_by(WorkoutSession.date, StrengthSet.id)
    ).all()

    weight: dict[int, dict[dt.date, float]] = {}
    one_rm: dict[int, dict[dt.date, float]] = {}
    ex_tonnage: dict[int, dict[dt.date, float]] = {}
    grp_tonnage: dict[int | None, dict[dt.date, float]] = {}

    for date, eid, sid, w, reps in rows:
        if eid is None:  # подход без упражнения — не ряд по упражнению
            continue
        if w and w > 0:
            wd = weight.setdefault(eid, {})
            wd[date] = max(wd.get(date, 0.0), w)
        if w and reps and w > 0 and reps > 0:
            ton = w * reps
            ed = ex_tonnage.setdefault(eid, {})
            ed[date] = ed.get(date, 0.0) + ton
            gd = grp_tonnage.setdefault(sid, {})
            gd[date] = gd.get(date, 0.0) + ton
            est = epley_1rm(w, reps)
            if est is not None:
                rd = one_rm.setdefault(eid, {})
                rd[date] = max(rd.get(date, 0.0), est)

    ex_ids = sorted(set(weight) | set(one_rm) | set(ex_tonnage))
    by_exercise = [
        ExerciseStrengthSeries(
            exercise_id=eid,
            working_weight=_points(weight.get(eid, {})),
            best_1rm=_points(one_rm.get(eid, {})),
            tonnage=_points(ex_tonnage.get(eid, {})),
        )
        for eid in ex_ids
    ]
    by_group = [
        GroupTonnageSeries(sport_id=sid, tonnage=_points(grp_tonnage[sid]))
        for sid in sorted(grp_tonnage, key=lambda s: (s is None, s or 0))
    ]

    return StrengthProgressOut(start=start, end=end, by_exercise=by_exercise, by_group=by_group)


def _cardio_points(items, guard_key: str, value, ndigits: int = 2) -> list[SeriesPoint]:
    """Ряд из (дата, аккумулятор): точка только где знаменатель/величина (>0) есть."""
    return [
        SeriesPoint(date=d, value=round(value(a), ndigits)) for d, a in items if a[guard_key] > 0
    ]


class ExerciseCardioSeries(BaseModel):
    exercise_id: int | None
    distance: list[SeriesPoint]  # км/день (сумма)
    pace: list[SeriesPoint]  # темп сек/км (сумма времени / сумма дистанции за день)
    avg_hr: list[SeriesPoint]  # средний пульс за день
    efficiency: list[SeriesPoint]  # пульсовая эффективность: метров на удар сердца


class CardioProgressOut(BaseModel):
    start: dt.date
    end: dt.date
    by_exercise: list[ExerciseCardioSeries]


@router.get("/cardio")
def get_cardio_progress(
    session: SessionDep,
    user: CurrentUser,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> CardioProgressOut:
    start, end = _resolve_range(start, end)

    rows = session.exec(
        select(
            WorkoutSession.date,
            CardioLog.exercise_id,
            CardioLog.distance_km,
            CardioLog.duration_sec,
            CardioLog.avg_hr,
        )
        .select_from(CardioLog)
        .join(WorkoutSession, CardioLog.session_id == WorkoutSession.id)
        .where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.date >= start,
            WorkoutSession.date <= end,
        )
        .order_by(WorkoutSession.date, CardioLog.id)
    ).all()

    # На (упражнение, день) копим компоненты, производные ряды считаем в конце.
    acc: dict[tuple[int | None, dt.date], dict[str, float]] = {}
    for date, eid, dist_km, dur_sec, hr in rows:
        a = acc.setdefault(
            (eid, date),
            {
                "dist": 0.0,
                "p_dist": 0.0,
                "p_dur": 0.0,
                "hr_sum": 0.0,
                "hr_cnt": 0.0,
                "e_dist_m": 0.0,
                "e_beats": 0.0,
            },
        )
        if dist_km and dist_km > 0:
            a["dist"] += dist_km
        if dist_km and dur_sec and dist_km > 0 and dur_sec > 0:
            a["p_dist"] += dist_km
            a["p_dur"] += dur_sec
        if hr and hr > 0:
            a["hr_sum"] += hr
            a["hr_cnt"] += 1
        if dist_km and dur_sec and hr and dist_km > 0 and dur_sec > 0 and hr > 0:
            a["e_dist_m"] += dist_km * 1000
            a["e_beats"] += hr * dur_sec / 60  # ударов за заход ≈ пульс * минуты

    ex_ids = sorted({k[0] for k in acc}, key=lambda s: (s is None, s or 0))
    by_exercise: list[ExerciseCardioSeries] = []
    for eid in ex_ids:
        items = sorted((d, a) for (e, d), a in acc.items() if e == eid)
        by_exercise.append(
            ExerciseCardioSeries(
                exercise_id=eid,
                distance=_cardio_points(items, "dist", lambda a: a["dist"]),
                pace=_cardio_points(items, "p_dist", lambda a: a["p_dur"] / a["p_dist"]),
                avg_hr=_cardio_points(items, "hr_cnt", lambda a: a["hr_sum"] / a["hr_cnt"], 1),
                efficiency=_cardio_points(items, "e_beats", lambda a: a["e_dist_m"] / a["e_beats"]),
            )
        )

    return CardioProgressOut(start=start, end=end, by_exercise=by_exercise)
