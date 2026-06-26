"""PR-движок (S3.10): метрики силовой/кардио + детект персональных рекордов.

Чистые функции считают оценку 1ПМ (Epley: w*(1+reps/30)), тоннаж (sum w*reps) и объём
по упражнению. `*_candidates` извлекают рекорды-кандидаты из подходов/кардио-лога;
`apply_prs` сравнивает кандидата с лучшим personal_record того же упражнения и метрики и
пишет новую запись ТОЛЬКО при реальном улучшении (для темпа меньше = лучше).
"""

from collections.abc import Iterable
from dataclasses import dataclass

from sqlmodel import Session, select

from app.models.workout import PersonalRecord

# метрика -> (единица, выше=лучше). Темп храним в сек/км: меньше — лучше.
METRICS: dict[str, tuple[str, bool]] = {
    "max_weight": ("кг", True),
    "best_1rm": ("кг", True),
    "best_pace": ("сек/км", False),
    "max_distance": ("км", True),
}


@dataclass(frozen=True)
class PRCandidate:
    exercise_id: int
    metric: str
    value: float


def epley_1rm(weight_kg: float | None, reps: int | None) -> float | None:
    """Оценка 1ПМ по Эпли: w*(1+reps/30). Без валидного веса/повторов оценки нет."""
    if not weight_kg or not reps or weight_kg <= 0 or reps <= 0:
        return None
    return round(weight_kg * (1 + reps / 30), 2)


def tonnage(sets: Iterable) -> float:
    """Тоннаж = сумма w*reps по подходам, где есть и вес (>0), и повторы (>0)."""
    return round(sum(s.weight_kg * s.reps for s in sets if s.weight_kg and s.reps), 2)


def volume_by_exercise(sets: Iterable) -> dict[int, float]:
    """Объём (тоннаж) по каждому упражнению: exercise_id -> sum(w*reps)."""
    vols: dict[int, float] = {}
    for s in sets:
        if s.weight_kg and s.reps:
            vols[s.exercise_id] = round(vols.get(s.exercise_id, 0.0) + s.weight_kg * s.reps, 2)
    return vols


def strength_candidates(sets: Iterable) -> list[PRCandidate]:
    """Кандидаты в PR по силовой сессии: на упражнение — макс вес и лучший 1ПМ.

    Учитываем только подходы с весом и повторами (без них рекорд недостоверен).
    """
    best_weight: dict[int, float] = {}
    best_1rm: dict[int, float] = {}
    for s in sets:
        one_rm = epley_1rm(s.weight_kg, s.reps)
        if one_rm is None:
            continue
        eid = s.exercise_id
        if s.weight_kg > best_weight.get(eid, 0.0):
            best_weight[eid] = s.weight_kg
        if one_rm > best_1rm.get(eid, 0.0):
            best_1rm[eid] = one_rm

    out: list[PRCandidate] = []
    out += [PRCandidate(eid, "max_weight", round(w, 2)) for eid, w in best_weight.items()]
    out += [PRCandidate(eid, "best_1rm", v) for eid, v in best_1rm.items()]
    return out


def cardio_candidates(log) -> list[PRCandidate]:
    """Кандидаты в PR по кардио: лучший темп (сек/км) и макс дистанция.

    Рекорды привязаны к упражнению — без exercise_id кандидатов нет.
    """
    if log.exercise_id is None:
        return []
    out: list[PRCandidate] = []
    if log.distance_km and log.distance_km > 0:
        out.append(PRCandidate(log.exercise_id, "max_distance", round(log.distance_km, 2)))
        if log.duration_sec and log.duration_sec > 0:
            pace = round(log.duration_sec / log.distance_km, 2)
            out.append(PRCandidate(log.exercise_id, "best_pace", pace))
    return out


def _is_improvement(value: float, current: float | None, higher_is_better: bool) -> bool:
    """Новый PR только при строгом улучшении; первый результат по метрике — всегда рекорд."""
    if current is None:
        return True
    return value > current if higher_is_better else value < current


def _current_best(
    session: Session, exercise_id: int, metric: str, higher: bool, user_id: int
) -> float | None:
    rows = session.exec(
        select(PersonalRecord.value)
        .where(PersonalRecord.exercise_id == exercise_id)
        .where(PersonalRecord.metric == metric)
        .where(PersonalRecord.user_id == user_id)  # рекорды владельца, не чужие (изоляция M0)
    ).all()
    if not rows:
        return None
    return max(rows) if higher else min(rows)


def apply_prs(
    session: Session, candidates: Iterable[PRCandidate], date, user_id: int
) -> list[PersonalRecord]:
    """Записать те кандидаты, что реально побили текущий рекорд. Возвращает новые записи."""
    new_records: list[PersonalRecord] = []
    for c in candidates:
        unit, higher = METRICS[c.metric]
        current = _current_best(session, c.exercise_id, c.metric, higher, user_id)
        if not _is_improvement(c.value, current, higher):
            continue
        rec = PersonalRecord(
            user_id=user_id,
            exercise_id=c.exercise_id,
            metric=c.metric,
            date=date,
            value=c.value,
            unit=unit,
        )
        session.add(rec)
        new_records.append(rec)
    if new_records:
        session.commit()
        for rec in new_records:
            session.refresh(rec)
    return new_records
