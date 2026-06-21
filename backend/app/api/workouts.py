"""Логирование тренировок: силовая (S3.4), кардио (S3.5), скилловые (S3.6).

Силовая: POST /workouts создаёт workout_session и все strength_set'ы (≥1 подход),
пишет вес/повторы/отдых/RPE и возвращает сессию с подходами.

Кардио (S3.5): POST /workouts/cardio создаёт сессию + cardio_log
(distance_km, duration_sec, avg_hr, max_hr); темп (avg_pace) считается из дистанции/времени
и сохраняется как снимок. GET /workouts/cardio/{id} читает её обратно.

Скилловые (S3.6): POST /workouts/skill создаёт сессию + skill_log'и (≥1 элемент),
каждый пишет попытки/приземления (attempts, landed) по элементу (вейкборд/BMX/эндуро).
GET /workouts/skill/{id} читает сессию обратно; GET /workouts/skill/progress
агрегирует прогресс по элементам (сумма попыток/приземлений и доля удачных).

Каждая запись ссылается на упражнение/вид спорта (FK); несуществующий FK → 404 (SQLite сам не
проверяет). Все роуты под сессией (CurrentUser) — приложение однопользовательское.
"""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session, select

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.models.sport import Exercise, Sport
from app.models.workout import CardioLog, SkillLog, StrengthSet, WorkoutSession

router = APIRouter(prefix="/workouts", tags=["workouts"])

SessionDep = Annotated[Session, Depends(get_session)]


class StrengthSetIn(BaseModel):
    exercise_id: int
    set_index: int | None = None
    weight_kg: float | None = None
    reps: int | None = None
    rest_sec: float | None = None  # отдых после подхода, сек
    rpe: float | None = None  # субъективная интенсивность (0–10)


class WorkoutCreate(BaseModel):
    date: dt.date
    sport_id: int | None = None
    title: str | None = None
    notes: str | None = None
    sets: list[StrengthSetIn] = Field(min_length=1)  # силовая сессия без подходов бессмысленна


class StrengthSetRead(BaseModel):
    id: int
    exercise_id: int
    set_index: int | None
    weight_kg: float | None
    reps: int | None
    rest_sec: float | None
    rpe: float | None


class WorkoutRead(BaseModel):
    id: int
    date: dt.date
    sport_id: int | None
    title: str | None
    notes: str | None
    created_at: dt.datetime
    sets: list[StrengthSetRead]


def _require_sport(session: Session, sport_id: int) -> None:
    if session.get(Sport, sport_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Вид спорта не найден")


def _require_exercises(session: Session, exercise_ids: set[int]) -> None:
    """Каждый подход должен ссылаться на существующее упражнение — иначе осиротевшая строка."""
    for exercise_id in exercise_ids:
        if session.get(Exercise, exercise_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Упражнение {exercise_id} не найдено",
            )


def _read(session: Session, ws: WorkoutSession) -> WorkoutRead:
    sets = session.exec(
        select(StrengthSet)
        .where(StrengthSet.session_id == ws.id)
        .order_by(StrengthSet.set_index, StrengthSet.id)
    ).all()
    return WorkoutRead(
        **ws.model_dump(),
        sets=[StrengthSetRead.model_validate(s.model_dump()) for s in sets],
    )


def _get_or_404(session: Session, workout_id: int) -> WorkoutSession:
    ws = session.get(WorkoutSession, workout_id)
    if ws is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тренировка не найдена")
    return ws


@router.post("", status_code=status.HTTP_201_CREATED)
def create_workout(payload: WorkoutCreate, session: SessionDep, _: CurrentUser) -> WorkoutRead:
    if payload.sport_id is not None:
        _require_sport(session, payload.sport_id)
    _require_exercises(session, {s.exercise_id for s in payload.sets})

    ws = WorkoutSession(
        date=payload.date, sport_id=payload.sport_id, title=payload.title, notes=payload.notes
    )
    session.add(ws)
    session.commit()
    session.refresh(ws)

    for item in payload.sets:
        session.add(StrengthSet(session_id=ws.id, **item.model_dump()))
    session.commit()

    return _read(session, ws)


@router.get("")
def list_workouts(session: SessionDep, _: CurrentUser) -> list[WorkoutRead]:
    sessions = session.exec(
        select(WorkoutSession).order_by(WorkoutSession.date.desc(), WorkoutSession.id.desc())
    ).all()
    return [_read(session, ws) for ws in sessions]


@router.get("/{workout_id}")
def get_workout(workout_id: int, session: SessionDep, _: CurrentUser) -> WorkoutRead:
    return _read(session, _get_or_404(session, workout_id))


# --- Кардио (S3.5) ---


class CardioIn(BaseModel):
    date: dt.date
    sport_id: int | None = None
    exercise_id: int | None = None
    title: str | None = None
    notes: str | None = None
    distance_km: float = Field(gt=0)  # без дистанции темп не посчитать
    duration_sec: float = Field(gt=0)  # без времени темп не посчитать
    avg_hr: int | None = None
    max_hr: int | None = None


class CardioRead(BaseModel):
    id: int
    session_id: int
    date: dt.date
    sport_id: int | None
    exercise_id: int | None
    title: str | None
    notes: str | None
    created_at: dt.datetime
    distance_km: float | None
    duration_sec: float | None
    avg_hr: int | None
    max_hr: int | None
    avg_pace: str | None


def _compute_pace(distance_km: float, duration_sec: float) -> str | None:
    """Темп = время/дистанция → "M:SS /км". Без валидной дистанции/времени темпа нет."""
    if distance_km <= 0 or duration_sec <= 0:
        return None
    sec_per_km = round(duration_sec / distance_km)
    return f"{sec_per_km // 60}:{sec_per_km % 60:02d} /км"


def _read_cardio(ws: WorkoutSession, log: CardioLog) -> CardioRead:
    return CardioRead(
        id=log.id,
        session_id=ws.id,
        date=ws.date,
        sport_id=ws.sport_id,
        exercise_id=log.exercise_id,
        title=ws.title,
        notes=ws.notes,
        created_at=ws.created_at,
        distance_km=log.distance_km,
        duration_sec=log.duration_sec,
        avg_hr=log.avg_hr,
        max_hr=log.max_hr,
        avg_pace=log.avg_pace,
    )


@router.post("/cardio", status_code=status.HTTP_201_CREATED)
def create_cardio(payload: CardioIn, session: SessionDep, _: CurrentUser) -> CardioRead:
    if payload.sport_id is not None:
        _require_sport(session, payload.sport_id)
    if payload.exercise_id is not None:
        _require_exercises(session, {payload.exercise_id})

    ws = WorkoutSession(
        date=payload.date, sport_id=payload.sport_id, title=payload.title, notes=payload.notes
    )
    session.add(ws)
    session.commit()
    session.refresh(ws)

    log = CardioLog(
        session_id=ws.id,
        exercise_id=payload.exercise_id,
        distance_km=payload.distance_km,
        duration_sec=payload.duration_sec,
        avg_hr=payload.avg_hr,
        max_hr=payload.max_hr,
        avg_pace=_compute_pace(payload.distance_km, payload.duration_sec),
    )
    session.add(log)
    session.commit()
    session.refresh(log)

    return _read_cardio(ws, log)


@router.get("/cardio/{cardio_id}")
def get_cardio(cardio_id: int, session: SessionDep, _: CurrentUser) -> CardioRead:
    log = session.get(CardioLog, cardio_id)
    if log is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Кардио-сессия не найдена"
        )
    ws = session.get(WorkoutSession, log.session_id)
    return _read_cardio(ws, log)


# --- Скилловые/элементы (S3.6) ---


class SkillEntryIn(BaseModel):
    exercise_id: int  # элемент: трюк/фигура (вейкборд, BMX, эндуро…)
    attempts: int = Field(ge=1)  # без попыток нечего логировать
    landed: int = Field(ge=0)  # удачных приземлений
    notes: str | None = None

    @model_validator(mode="after")
    def _landed_within_attempts(self) -> "SkillEntryIn":
        if self.landed > self.attempts:
            raise ValueError("landed не может превышать attempts")
        return self


class SkillCreate(BaseModel):
    date: dt.date
    sport_id: int | None = None
    title: str | None = None
    notes: str | None = None
    entries: list[SkillEntryIn] = Field(min_length=1)  # скилл-сессия без элементов бессмысленна


class SkillEntryRead(BaseModel):
    id: int
    exercise_id: int
    attempts: int | None
    landed: int | None
    notes: str | None


class SkillRead(BaseModel):
    id: int
    date: dt.date
    sport_id: int | None
    title: str | None
    notes: str | None
    created_at: dt.datetime
    entries: list[SkillEntryRead]


class SkillProgressItem(BaseModel):
    exercise_id: int
    exercise_name: str
    attempts: int  # суммарно попыток по элементу
    landed: int  # суммарно удачных
    landing_rate: float  # landed / attempts, 0..1
    sessions: int  # в скольких сессиях встречался элемент


def _read_skill(session: Session, ws: WorkoutSession) -> SkillRead:
    entries = session.exec(
        select(SkillLog).where(SkillLog.session_id == ws.id).order_by(SkillLog.id)
    ).all()
    return SkillRead(
        **ws.model_dump(),
        entries=[SkillEntryRead.model_validate(e.model_dump()) for e in entries],
    )


@router.post("/skill", status_code=status.HTTP_201_CREATED)
def create_skill(payload: SkillCreate, session: SessionDep, _: CurrentUser) -> SkillRead:
    if payload.sport_id is not None:
        _require_sport(session, payload.sport_id)
    _require_exercises(session, {e.exercise_id for e in payload.entries})

    ws = WorkoutSession(
        date=payload.date, sport_id=payload.sport_id, title=payload.title, notes=payload.notes
    )
    session.add(ws)
    session.commit()
    session.refresh(ws)

    for item in payload.entries:
        session.add(SkillLog(session_id=ws.id, **item.model_dump()))
    session.commit()

    return _read_skill(session, ws)


@router.get("/skill/progress")
def skill_progress(session: SessionDep, _: CurrentUser) -> list[SkillProgressItem]:
    """Прогресс по элементам: суммируем попытки/приземления по каждому упражнению."""
    logs = session.exec(select(SkillLog)).all()

    agg: dict[int, dict] = {}
    for log in logs:
        acc = agg.setdefault(log.exercise_id, {"attempts": 0, "landed": 0, "sessions": set()})
        acc["attempts"] += log.attempts or 0
        acc["landed"] += log.landed or 0
        acc["sessions"].add(log.session_id)

    items: list[SkillProgressItem] = []
    for exercise_id in sorted(agg):
        acc = agg[exercise_id]
        attempts = acc["attempts"]
        ex = session.get(Exercise, exercise_id)
        items.append(
            SkillProgressItem(
                exercise_id=exercise_id,
                exercise_name=ex.name if ex else f"#{exercise_id}",
                attempts=attempts,
                landed=acc["landed"],
                landing_rate=round(acc["landed"] / attempts, 3) if attempts else 0.0,
                sessions=len(acc["sessions"]),
            )
        )
    return items


@router.get("/skill/{skill_id}")
def get_skill(skill_id: int, session: SessionDep, _: CurrentUser) -> SkillRead:
    ws = session.get(WorkoutSession, skill_id)
    has_entries = (
        ws is not None
        and session.exec(select(SkillLog).where(SkillLog.session_id == skill_id).limit(1)).first()
        is not None
    )
    if not has_entries:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Скилл-сессия не найдена")
    return _read_skill(session, ws)
