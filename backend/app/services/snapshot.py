"""Агрегатор входа для LLM (S4.1): один снапшот со всеми сигналами трекера.

`build_snapshot(session)` собирает в один сериализуемый dict всё, что нужно модели
для рекомендации (поле `recommendation.input_snapshot_json`): активную SMART-цель и
прогресс к ней, тренды еды/макросов, активность и дефицит, последние замеры тела и
InBody (с динамикой), сводку тренировок (силовые/кардио) и текущие персональные
рекорды.

Главный инвариант карточки — устойчивость к пропускам: любая таблица может быть
пустой, любое поле — null. Тогда секция отдаёт None / пустой список / нулевой
счётчик, но снапшот всегда собирается целиком (никаких исключений на отсутствии
данных). Значения — компактные сводки (средние / последние / дельты), а не сырые
ряды: LLM нужен сигнал, а не сотни точек. Даты сериализуются в ISO-строки, чтобы
снапшот клался в JSON-колонку и отдавался через API без доработок.
"""

import datetime as dt
from collections import Counter
from typing import Any

from sqlalchemy import func
from sqlmodel import Session, select

from app.models._time import utcnow
from app.models.activity import ActivityDay
from app.models.body import BodyMeasurement, InbodyMeasurement
from app.models.deficit import DeficitDay
from app.models.goal import GoalStatus, SmartGoal
from app.models.nutrition import FoodEntry
from app.models.sport import Exercise, Sport
from app.models.workout import CardioLog, PersonalRecord, StrengthSet, WorkoutSession
from app.services.workout_metrics import METRICS, epley_1rm

DEFAULT_WINDOW_DAYS = 90
# Короткое «недавнее» окно поверх основного — даёт LLM направление тренда питания.
RECENT_DAYS = 14

# Обхваты body_measurement, идущие в снапшот как сигнал (height/notes — не метрики).
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
INBODY_FIELDS = ("weight_kg", "body_fat_pct", "muscle_mass_kg", "visceral_fat", "water")


def build_snapshot(
    session: Session,
    *,
    user_id: int,
    end: dt.date | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> dict[str, Any]:
    """Снапшот владельца (user_id) со всеми сигналами за окно [end-window_days+1; end].

    Любая секция устойчива к отсутствию данных. `end` по умолчанию — сегодня. Все
    секции читают только записи user_id — снапшот для LLM собирается по одному
    пользователю (каталоги sport/exercise общие и не скоупятся).
    """
    end = end or dt.date.today()
    start = end - dt.timedelta(days=window_days - 1)
    return {
        "generated_at": utcnow().isoformat(),
        "window": {"start": _iso(start), "end": _iso(end), "days": window_days},
        "goal": _build_goal(session, end, user_id),
        "nutrition": _build_nutrition(session, start, end, user_id),
        "activity": _build_activity(session, start, end, user_id),
        "measurements": _build_measurements(session, start, end, user_id),
        "inbody": _build_inbody(session, start, end, user_id),
        "training": _build_training(session, start, end, user_id),
        "personal_records": _build_prs(session, user_id),
    }


# --- общие хелперы -----------------------------------------------------------


def _iso(value: dt.date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _avg(values: list[float | int | None], ndigits: int = 1) -> float | None:
    """Среднее по не-null значениям; пусто → None (без ложного нуля)."""
    nums = [v for v in values if v is not None]
    return round(sum(nums) / len(nums), ndigits) if nums else None


def _round(value: float | None, ndigits: int = 1) -> float | None:
    return None if value is None else round(value, ndigits)


def _percent(baseline: float | None, current: float | None, target: float) -> float | None:
    """Доля пути baseline→target в %, направление любое, зажата в 0..100."""
    if baseline is None or current is None:
        return None
    denom = target - baseline
    if denom == 0:  # база уже на цели — считаем достигнутой
        return 100.0
    pct = (current - baseline) / denom * 100
    return round(min(100.0, max(0.0, pct)), 1)


def _exercise_names(session: Session) -> dict[int, str]:
    """{exercise_id: name} для подписи рядов; пусто, если упражнений нет."""
    return {e.id: e.name for e in session.exec(select(Exercise)).all() if e.id is not None}


# --- цель и прогресс к ней ---------------------------------------------------


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_body_col(key: str) -> str | None:
    """Ключ цели (waist) → колонка body_measurement (waist_cm); None если нет."""
    for candidate in (key, f"{key}_cm"):
        if hasattr(BodyMeasurement, candidate):
            return candidate
    return None


def _baseline_lookup(baseline_json: dict[str, Any] | None, keys: tuple[str, ...]) -> float | None:
    if not baseline_json:
        return None
    for key in keys:
        if baseline_json.get(key) is not None:
            return _to_float(baseline_json[key])
    return None


def _metric_progress(
    session: Session,
    *,
    model: type,
    col: str,
    target: float,
    today: dt.date,
    label: str,
    baseline_keys: tuple[str, ...],
    baseline_json: dict[str, Any] | None,
    start_date: dt.date | None,
    user_id: int,
) -> dict[str, Any]:
    """Прогресс по одной метрике цели владельца: baseline→current→target, % и остаток.

    Метрика без единого замера отдаёт current/percent = None (устойчивость к
    пропускам). baseline_json@start_date добавляется как самый ранний синтетический
    замер, только если он раньше первого реального — иначе темп считается неверно.
    """
    column = getattr(model, col)
    conds = [column.is_not(None), model.date <= today, model.user_id == user_id]
    if start_date is not None:
        conds.append(model.date >= start_date)
    rows = session.exec(
        select(model.date, column).where(*conds).order_by(model.date, model.id)
    ).all()
    points = [(d, float(v)) for d, v in rows]

    bjson = _baseline_lookup(baseline_json, baseline_keys)
    if bjson is not None and start_date is not None and points and start_date < points[0][0]:
        points = [(start_date, bjson), *points]

    baseline = points[0][1] if points else None
    current = points[-1][1] if points else None
    return {
        "metric": label,
        "target": round(float(target), 1),
        "baseline": _round(baseline),
        "current": _round(current),
        "remaining": None if current is None else round(abs(target - current), 1),
        "percent": _percent(baseline, current, target),
    }


def _build_goal(session: Session, today: dt.date, user_id: int) -> dict[str, Any] | None:
    goal = session.exec(
        select(SmartGoal).where(SmartGoal.status == GoalStatus.active, SmartGoal.user_id == user_id)
    ).first()
    if goal is None:
        return None

    progress: list[dict[str, Any]] = []
    if goal.target_weight_kg is not None:
        progress.append(
            _metric_progress(
                session,
                model=InbodyMeasurement,
                col="weight_kg",
                target=goal.target_weight_kg,
                today=today,
                label="weight_kg",
                baseline_keys=("weight_kg",),
                baseline_json=goal.baseline_json,
                start_date=goal.start_date,
                user_id=user_id,
            )
        )
    if goal.target_body_fat_pct is not None:
        progress.append(
            _metric_progress(
                session,
                model=InbodyMeasurement,
                col="body_fat_pct",
                target=goal.target_body_fat_pct,
                today=today,
                label="body_fat_pct",
                baseline_keys=("body_fat_pct",),
                baseline_json=goal.baseline_json,
                start_date=goal.start_date,
                user_id=user_id,
            )
        )
    for key, raw_target in (goal.target_measurements_json or {}).items():
        col = _resolve_body_col(key)
        target = _to_float(raw_target)
        if col is None or target is None:  # цель на неизмеримую колонку — пропускаем
            continue
        progress.append(
            _metric_progress(
                session,
                model=BodyMeasurement,
                col=col,
                target=target,
                today=today,
                label=col,
                baseline_keys=(key, col),
                baseline_json=goal.baseline_json,
                start_date=goal.start_date,
                user_id=user_id,
            )
        )

    return {
        "id": goal.id,
        "target_weight_kg": goal.target_weight_kg,
        "target_body_fat_pct": goal.target_body_fat_pct,
        "target_measurements": goal.target_measurements_json or {},
        "start_date": _iso(goal.start_date),
        "deadline": _iso(goal.deadline),
        "why_notes": goal.why_notes,
        "progress": progress,
    }


# --- питание / макросы -------------------------------------------------------


def _daily_food(session: Session, start: dt.date, end: dt.date, user_id: int) -> list[tuple]:
    """Суммы за день владельца: (date, kcal, protein, fat, carb). SUM=None, если пусто."""
    return session.exec(
        select(
            FoodEntry.date,
            func.sum(FoodEntry.kcal),
            func.sum(FoodEntry.protein_g),
            func.sum(FoodEntry.fat_g),
            func.sum(FoodEntry.carb_g),
        )
        .where(FoodEntry.date >= start, FoodEntry.date <= end, FoodEntry.user_id == user_id)
        .group_by(FoodEntry.date)
        .order_by(FoodEntry.date)
    ).all()


def _avg_food(rows: list[tuple]) -> dict[str, Any]:
    return {
        "days": sum(1 for r in rows if r[1] is not None),
        "avg_kcal_in": _avg([r[1] for r in rows]),
        "avg_protein_g": _avg([r[2] for r in rows]),
        "avg_fat_g": _avg([r[3] for r in rows]),
        "avg_carb_g": _avg([r[4] for r in rows]),
    }


def _build_nutrition(
    session: Session, start: dt.date, end: dt.date, user_id: int
) -> dict[str, Any]:
    rows = _daily_food(session, start, end, user_id)
    window = _avg_food(rows)
    recent_start = end - dt.timedelta(days=RECENT_DAYS - 1)
    recent = _avg_food([r for r in rows if r[0] >= recent_start])
    return {"logged_days": window.pop("days"), **window, "recent": recent}


# --- активность / дефицит ----------------------------------------------------


def _build_activity(session: Session, start: dt.date, end: dt.date, user_id: int) -> dict[str, Any]:
    rows = session.exec(
        select(ActivityDay.date, ActivityDay.total_kcal, ActivityDay.steps, ActivityDay.moving_min)
        .where(ActivityDay.date >= start, ActivityDay.date <= end, ActivityDay.user_id == user_id)
        .order_by(ActivityDay.date)
    ).all()
    deficits = session.exec(
        select(DeficitDay.deficit_kcal)
        .where(
            DeficitDay.date >= start,
            DeficitDay.date <= end,
            DeficitDay.deficit_kcal.is_not(None),
            DeficitDay.user_id == user_id,
        )
        .order_by(DeficitDay.date)
    ).all()
    return {
        "logged_days": len(rows),
        "avg_kcal_out": _avg([r[1] for r in rows]),
        "avg_steps": _avg([r[2] for r in rows]),
        "avg_moving_min": _avg([r[3] for r in rows]),
        "deficit": {
            "complete_days": len(deficits),
            "avg_deficit_kcal": _avg(deficits),
            "total_deficit_kcal": sum(deficits) if deficits else None,
        },
    }


# --- замеры тела / InBody ----------------------------------------------------


def _current_change(rows: list, fields: tuple[str, ...]) -> dict[str, dict[str, float]]:
    """По каждому полю: {current: последний, change: последний − первый} в окне.

    `rows` отсортированы по дате. Поля без единого не-null значения пропускаются —
    раздел остаётся непустым ровно настолько, насколько есть данные.
    """
    out: dict[str, dict[str, float]] = {}
    for field in fields:
        series = [getattr(m, field) for m in rows if getattr(m, field) is not None]
        if not series:
            continue
        out[field] = {"current": _round(series[-1]), "change": round(series[-1] - series[0], 1)}
    return out


def _build_measurements(
    session: Session, start: dt.date, end: dt.date, user_id: int
) -> dict[str, Any]:
    rows = session.exec(
        select(BodyMeasurement)
        .where(
            BodyMeasurement.date >= start,
            BodyMeasurement.date <= end,
            BodyMeasurement.user_id == user_id,
        )
        .order_by(BodyMeasurement.date, BodyMeasurement.id)
    ).all()
    latest = max((m.date for m in rows), default=None)
    return {"latest_date": _iso(latest), "values": _current_change(rows, CIRCUMFERENCE_FIELDS)}


def _build_inbody(
    session: Session, start: dt.date, end: dt.date, user_id: int
) -> dict[str, Any] | None:
    rows = session.exec(
        select(InbodyMeasurement)
        .where(
            InbodyMeasurement.date >= start,
            InbodyMeasurement.date <= end,
            InbodyMeasurement.user_id == user_id,
        )
        .order_by(InbodyMeasurement.date, InbodyMeasurement.id)
    ).all()
    if not rows:
        return None
    return {"latest_date": _iso(rows[-1].date), "values": _current_change(rows, INBODY_FIELDS)}


# --- тренировки: силовые / кардио --------------------------------------------


def _strength_summary(
    session: Session, start: dt.date, end: dt.date, names: dict[int, str], user_id: int
) -> list[dict[str, Any]]:
    rows = session.exec(
        select(
            WorkoutSession.date,
            StrengthSet.exercise_id,
            StrengthSet.weight_kg,
            StrengthSet.reps,
        )
        .select_from(StrengthSet)
        .join(WorkoutSession, StrengthSet.session_id == WorkoutSession.id)
        .where(
            WorkoutSession.date >= start,
            WorkoutSession.date <= end,
            WorkoutSession.user_id == user_id,
        )
        .order_by(WorkoutSession.date, StrengthSet.id)
    ).all()

    per: dict[int, dict[str, Any]] = {}
    for date, eid, w, reps in rows:
        if eid is None:
            continue
        d = per.setdefault(
            eid, {"tonnage": 0.0, "best_1rm": 0.0, "last_date": None, "last_weight": None}
        )
        if w and w > 0:  # рабочий вес = макс на самой свежей дате
            if d["last_date"] is None or date > d["last_date"]:
                d["last_date"], d["last_weight"] = date, w
            elif date == d["last_date"]:
                d["last_weight"] = max(d["last_weight"], w)
        if w and reps and w > 0 and reps > 0:
            d["tonnage"] += w * reps
            est = epley_1rm(w, reps)
            if est is not None:
                d["best_1rm"] = max(d["best_1rm"], est)

    return [
        {
            "exercise_id": eid,
            "exercise_name": names.get(eid),
            "latest_working_weight": _round(d["last_weight"]),
            "best_1rm": round(d["best_1rm"], 2) if d["best_1rm"] else None,
            "total_tonnage": round(d["tonnage"], 2),
        }
        for eid, d in sorted(per.items())
    ]


def _cardio_summary(
    session: Session, start: dt.date, end: dt.date, names: dict[int, str], user_id: int
) -> list[dict[str, Any]]:
    rows = session.exec(
        select(
            CardioLog.exercise_id,
            CardioLog.distance_km,
            CardioLog.duration_sec,
            CardioLog.avg_hr,
        )
        .select_from(CardioLog)
        .join(WorkoutSession, CardioLog.session_id == WorkoutSession.id)
        .where(
            WorkoutSession.date >= start,
            WorkoutSession.date <= end,
            WorkoutSession.user_id == user_id,
        )
    ).all()

    per: dict[int | None, dict[str, Any]] = {}
    for eid, dist, dur, hr in rows:
        d = per.setdefault(eid, {"dist": 0.0, "p_dist": 0.0, "p_dur": 0.0, "hr": []})
        if dist and dist > 0:
            d["dist"] += dist
            if dur and dur > 0:
                d["p_dist"] += dist
                d["p_dur"] += dur
        if hr and hr > 0:
            d["hr"].append(hr)

    out: list[dict[str, Any]] = []
    for eid, d in sorted(per.items(), key=lambda kv: (kv[0] is None, kv[0] or 0)):
        out.append(
            {
                "exercise_id": eid,
                "exercise_name": names.get(eid) if eid is not None else None,
                "total_distance_km": round(d["dist"], 2) if d["dist"] else None,
                "avg_pace_sec_km": round(d["p_dur"] / d["p_dist"], 1) if d["p_dist"] else None,
                "avg_hr": _avg(d["hr"]),
            }
        )
    return out


def _build_training(session: Session, start: dt.date, end: dt.date, user_id: int) -> dict[str, Any]:
    sessions = session.exec(
        select(WorkoutSession).where(
            WorkoutSession.date >= start,
            WorkoutSession.date <= end,
            WorkoutSession.user_id == user_id,
        )
    ).all()
    sport_names = {s.id: s.name for s in session.exec(select(Sport)).all()}
    counts = Counter(s.sport_id for s in sessions)
    by_sport = [
        {"sport_id": sid, "sport_name": sport_names.get(sid), "sessions": n}
        for sid, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0] is None, kv[0] or 0))
    ]
    names = _exercise_names(session)
    return {
        "sessions": len(sessions),
        "by_sport": by_sport,
        "strength": _strength_summary(session, start, end, names, user_id),
        "cardio": _cardio_summary(session, start, end, names, user_id),
    }


# --- персональные рекорды ----------------------------------------------------


def _build_prs(session: Session, user_id: int) -> list[dict[str, Any]]:
    """Текущий лучший PR владельца на каждую пару (упражнение, метрика).

    Таблица хранит историю рекордов; здесь оставляем экстремум по направлению
    метрики (для темпа меньше = лучше). Нет рекордов → пустой список.
    """
    best: dict[tuple[int, str], PersonalRecord] = {}
    for rec in session.exec(select(PersonalRecord).where(PersonalRecord.user_id == user_id)).all():
        higher = METRICS.get(rec.metric, (None, True))[1]
        key = (rec.exercise_id, rec.metric)
        cur = best.get(key)
        if cur is None or (rec.value > cur.value if higher else rec.value < cur.value):
            best[key] = rec

    names = _exercise_names(session)
    return [
        {
            "exercise_id": rec.exercise_id,
            "exercise_name": names.get(rec.exercise_id),
            "metric": rec.metric,
            "value": rec.value,
            "unit": rec.unit,
            "date": _iso(rec.date),
        }
        for (_, _), rec in sorted(best.items(), key=lambda kv: (kv[0][0], kv[0][1]))
    ]
