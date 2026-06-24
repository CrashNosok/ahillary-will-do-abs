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
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session, select

from app.api.deps import CurrentUser
from app.core import db
from app.core.db import get_session
from app.models.activity import ActivityDay
from app.models.sport import Exercise, Sport
from app.models.workout import (
    CardioLog,
    PersonalRecord,
    SkillLog,
    StrengthSet,
    WorkoutMedia,
    WorkoutSession,
)
from app.services.workout_metrics import (
    apply_prs,
    cardio_candidates,
    epley_1rm,
    strength_candidates,
    tonnage,
)

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


class PersonalRecordRead(BaseModel):
    id: int
    exercise_id: int
    metric: str  # max_weight | best_1rm | best_pace | max_distance
    date: dt.date
    value: float
    unit: str | None


class WorkoutRead(BaseModel):
    id: int
    date: dt.date
    activity_date: dt.date | None  # связанный Welltory-день (S3.9), None если не размечен
    sport_id: int | None
    title: str | None
    notes: str | None
    created_at: dt.datetime
    sets: list[StrengthSetRead]
    # новые PR, зафиксированные этой сессией (флаг S3.10); заполняется только при создании
    personal_records: list[PersonalRecordRead] = []


def _link_activity_date(session: Session, date: dt.date) -> dt.date | None:
    """Автолинк к Welltory-дню (S3.9): дата, если за этот день есть activity_day, иначе None."""
    return date if session.get(ActivityDay, date) is not None else None


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


def _pr_reads(prs: list[PersonalRecord]) -> list[PersonalRecordRead]:
    return [PersonalRecordRead.model_validate(p.model_dump()) for p in prs]


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
def create_workout(payload: WorkoutCreate, session: SessionDep, user: CurrentUser) -> WorkoutRead:
    if payload.sport_id is not None:
        _require_sport(session, payload.sport_id)
    _require_exercises(session, {s.exercise_id for s in payload.sets})

    ws = WorkoutSession(
        user_id=user.id,
        date=payload.date,
        activity_date=_link_activity_date(session, payload.date),
        sport_id=payload.sport_id,
        title=payload.title,
        notes=payload.notes,
    )
    session.add(ws)
    session.commit()
    session.refresh(ws)

    for item in payload.sets:
        session.add(StrengthSet(session_id=ws.id, **item.model_dump()))
    session.commit()

    # PR-движок (S3.10): фиксируем новые рекорды (макс вес / лучший 1ПМ) по сессии
    new_prs = apply_prs(session, strength_candidates(payload.sets), payload.date, user.id)
    return _read(session, ws).model_copy(update={"personal_records": _pr_reads(new_prs)})


# --- Минимальный («быстрый») лог тренировки (S3.11) -------------------------------------
# Тип/длительность/усилие пишутся прямо в workout_session (kind/duration_min/rpe), без таблиц
# подходов. Опционально прикрепляются медиа (фото зала / видео трюка) — файл на диск, путь в БД.

_SIMPLE_KINDS = {"cardio", "strength", "skill", "other"}
# Принимаем любые image/* и video/* (как и фронт: accept="image/*,video/*") — телефонные HEIC/HEVC
# тоже проходят. Расширение для файла на диске берём из имени, иначе дефолт по типу.
_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif", ".avif", ".bmp"}
_VID_EXT = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv", ".hevc", ".3gp", ".ogv"}


def _media_kind(file: UploadFile) -> tuple[str, str] | None:
    """(media_type, suffix). Тип — по MIME-префиксу image/|video/, иначе по расширению имени.
    suffix — исходное расширение (сохраняем .heic/.mov и пр.), иначе дефолт. None → не медиа."""
    ct = (file.content_type or "").lower()
    ext = Path(file.filename or "").suffix.lower()
    if ct.startswith("image/") or ext in _IMG_EXT:
        return "image", ext or ".jpg"
    if ct.startswith("video/") or ext in _VID_EXT:
        return "video", ext or ".mp4"
    return None


class SimpleMediaRead(BaseModel):
    id: int
    media_type: str  # image | video


class SimpleWorkoutRead(BaseModel):
    id: int
    date: dt.date
    kind: str
    sport_id: int | None
    duration_min: float | None
    rpe: float | None
    notes: str | None
    created_at: dt.datetime
    media: list[SimpleMediaRead]


@router.post("/simple", status_code=status.HTTP_201_CREATED)
async def create_simple_workout(
    session: SessionDep,
    user: CurrentUser,
    kind: Annotated[str, Form()],
    date: Annotated[dt.date | None, Form()] = None,
    duration_min: Annotated[float | None, Form()] = None,
    sport_id: Annotated[int | None, Form()] = None,
    rpe: Annotated[float | None, Form()] = None,
    note: Annotated[str | None, Form()] = None,
    files: Annotated[list[UploadFile], File()] = [],  # noqa: B006 — FastAPI-зависимость, не мутируется
) -> SimpleWorkoutRead:
    if kind not in _SIMPLE_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Неизвестный тип тренировки"
        )
    if duration_min is not None and duration_min <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Длительность — положительное число минут",
        )
    if rpe is not None and not (0 <= rpe <= 10):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Усилие (RPE) — число от 0 до 10",
        )
    # Тип сам по себе ничего не фиксирует — нужна хоть какая-то «начинка»: время, заметка или медиа.
    note_clean = note.strip() if note else ""
    has_media = any(f and f.filename for f in files)
    if duration_min is None and not note_clean and not has_media:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Заполните хотя бы одно: длительность, заметку или фото/видео",
        )
    if sport_id is not None:
        _require_sport(session, sport_id)

    day = date or dt.date.today()
    ws = WorkoutSession(
        user_id=user.id,
        date=day,
        activity_date=_link_activity_date(session, day),
        sport_id=sport_id,
        kind=kind,
        duration_min=duration_min,
        rpe=rpe,
        notes=note_clean or None,
    )
    session.add(ws)
    session.commit()
    session.refresh(ws)

    media: list[WorkoutMedia] = []
    for file in files:
        if not file or not file.filename:
            continue  # пустой слот формы (браузер шлёт его, когда файл не выбран)
        data = await file.read()
        if not data:
            continue
        resolved = _media_kind(file)
        if resolved is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Поддерживаются изображения (JPEG/PNG/WebP/GIF) и видео (MP4/MOV/WebM)",
            )
        media_type, suffix = resolved
        dest = db.workout_media_dir() / f"{day.isoformat()}_{uuid.uuid4().hex[:8]}{suffix}"
        dest.write_bytes(data)
        media.append(
            WorkoutMedia(
                session_id=ws.id,
                media_path=str(dest.relative_to(db.BACKEND_DIR)),
                media_type=media_type,
            )
        )
    if media:
        for m in media:
            session.add(m)
        session.commit()
        for m in media:
            session.refresh(m)

    return SimpleWorkoutRead(
        id=ws.id,
        date=ws.date,
        kind=kind,
        sport_id=ws.sport_id,
        duration_min=ws.duration_min,
        rpe=ws.rpe,
        notes=ws.notes,
        created_at=ws.created_at,
        media=[SimpleMediaRead(id=m.id, media_type=m.media_type) for m in media],
    )


@router.get("/media/{media_id}")
def get_workout_media(media_id: int, session: SessionDep, _: CurrentUser) -> FileResponse:
    """Отдаёт сам файл медиа тренировки (media_type выводится из расширения)."""
    m = session.get(WorkoutMedia, media_id)
    if m is None or not m.media_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Медиа не найдено")
    path = Path(m.media_path)
    if not path.is_absolute():
        path = db.BACKEND_DIR / path
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл медиа отсутствует")
    return FileResponse(path)


@router.get("")
def list_workouts(session: SessionDep, _: CurrentUser) -> list[WorkoutRead]:
    sessions = session.exec(
        select(WorkoutSession).order_by(WorkoutSession.date.desc(), WorkoutSession.id.desc())
    ).all()
    return [_read(session, ws) for ws in sessions]


class ExerciseMetrics(BaseModel):
    exercise_id: int
    exercise_name: str
    sets: int
    tonnage: float
    max_weight: float | None  # макс рабочий вес в сессии, кг
    best_1rm: float | None  # лучшая оценка 1ПМ (Epley) в сессии, кг


class GroupMetrics(BaseModel):
    sport_id: int | None
    sport_name: str
    tonnage: float  # суммарный объём по группе (виду спорта)


class WorkoutMetrics(BaseModel):
    workout_id: int
    total_tonnage: float  # sum(w*reps) по всей сессии
    by_exercise: list[ExerciseMetrics]
    by_group: list[GroupMetrics]


@router.get("/prs")
def list_personal_records(session: SessionDep, _: CurrentUser) -> list[PersonalRecordRead]:
    """Все зафиксированные персональные рекорды (S3.10), свежие сверху."""
    rows = session.exec(
        select(PersonalRecord).order_by(PersonalRecord.date.desc(), PersonalRecord.id.desc())
    ).all()
    return [PersonalRecordRead.model_validate(r.model_dump()) for r in rows]


@router.get("/{workout_id}/metrics")
def get_workout_metrics(workout_id: int, session: SessionDep, _: CurrentUser) -> WorkoutMetrics:
    """1ПМ/тоннаж/объём силовой сессии: по упражнению и по группе (S3.10)."""
    _get_or_404(session, workout_id)
    sets = session.exec(select(StrengthSet).where(StrengthSet.session_id == workout_id)).all()

    by_ex: dict[int, list[StrengthSet]] = {}
    for s in sets:
        by_ex.setdefault(s.exercise_id, []).append(s)

    ex_metrics: list[ExerciseMetrics] = []
    group_tonnage: dict[int | None, float] = {}
    group_names: dict[int | None, str] = {}
    for eid in sorted(by_ex):
        ex_sets = by_ex[eid]
        ex = session.get(Exercise, eid)
        one_rms = [r for r in (epley_1rm(s.weight_kg, s.reps) for s in ex_sets) if r is not None]
        weights = [s.weight_kg for s in ex_sets if s.weight_kg and s.reps]
        ex_tonnage = tonnage(ex_sets)
        ex_metrics.append(
            ExerciseMetrics(
                exercise_id=eid,
                exercise_name=ex.name if ex else f"#{eid}",
                sets=len(ex_sets),
                tonnage=ex_tonnage,
                max_weight=round(max(weights), 2) if weights else None,
                best_1rm=max(one_rms) if one_rms else None,
            )
        )
        sport_id = ex.sport_id if ex else None
        group_tonnage[sport_id] = round(group_tonnage.get(sport_id, 0.0) + ex_tonnage, 2)
        if sport_id not in group_names:
            sport = session.get(Sport, sport_id) if sport_id is not None else None
            group_names[sport_id] = sport.name if sport else "—"

    by_group = [
        GroupMetrics(sport_id=sid, sport_name=group_names[sid], tonnage=group_tonnage[sid])
        for sid in sorted(group_tonnage, key=lambda x: (x is None, x))
    ]
    return WorkoutMetrics(
        workout_id=workout_id,
        total_tonnage=tonnage(sets),
        by_exercise=ex_metrics,
        by_group=by_group,
    )


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
    activity_date: dt.date | None  # связанный Welltory-день (S3.9)
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
    # новые PR (лучший темп / макс дистанция), зафиксированные этой сессией (флаг S3.10)
    personal_records: list[PersonalRecordRead] = []


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
        activity_date=ws.activity_date,
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
def create_cardio(payload: CardioIn, session: SessionDep, user: CurrentUser) -> CardioRead:
    if payload.sport_id is not None:
        _require_sport(session, payload.sport_id)
    if payload.exercise_id is not None:
        _require_exercises(session, {payload.exercise_id})

    ws = WorkoutSession(
        user_id=user.id,
        date=payload.date,
        activity_date=_link_activity_date(session, payload.date),
        sport_id=payload.sport_id,
        title=payload.title,
        notes=payload.notes,
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

    # PR-движок (S3.10): фиксируем лучший темп / макс дистанцию по упражнению
    new_prs = apply_prs(session, cardio_candidates(log), payload.date, user.id)
    return _read_cardio(ws, log).model_copy(update={"personal_records": _pr_reads(new_prs)})


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
    activity_date: dt.date | None  # связанный Welltory-день (S3.9)
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
def create_skill(payload: SkillCreate, session: SessionDep, user: CurrentUser) -> SkillRead:
    if payload.sport_id is not None:
        _require_sport(session, payload.sport_id)
    _require_exercises(session, {e.exercise_id for e in payload.entries})

    ws = WorkoutSession(
        user_id=user.id,
        date=payload.date,
        activity_date=_link_activity_date(session, payload.date),
        sport_id=payload.sport_id,
        title=payload.title,
        notes=payload.notes,
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
