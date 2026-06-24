"""Тренировки (S1.2): сессия и её записи по упражнениям + персональные рекорды.

workout_session — одна тренировка (FK sport_id). Внутри сессии лежат записи разных
типов, каждая ссылается на session (FK session_id) и на упражнение (FK exercise_id):
- strength_set — силовой подход (вес/повторы/RPE);
- cardio_log — кардио (дистанция/время/пульс);
- skill_log — элемент/навык (попытки/приземления, напр. вейкборд, BMX, эндуро).
personal_record — лучший результат по упражнению (FK exercise_id), вне сессии; поле
metric различает род рекорда (вес / 1ПМ / темп / дистанция) — PR-движок S3.10.
"""

import datetime as dt

from sqlmodel import Field, SQLModel

from app.models._time import utcnow


class WorkoutSession(SQLModel, table=True):
    __tablename__ = "workout_session"

    id: int | None = Field(default=None, primary_key=True)
    sport_id: int | None = Field(default=None, foreign_key="sport.id", index=True)
    date: dt.date = Field(index=True)
    # Связь с Welltory-днём (S3.9): FK на activity_day.date. Проставляется автолинком
    # при создании, если за этот день есть activity_day; иначе None («день не размечен»).
    activity_date: dt.date | None = Field(default=None, foreign_key="activity_day.date", index=True)
    title: str | None = None
    notes: str | None = None
    # Минимальный ручной ввод («быстрый лог», S3.11): тип/длительность/усилие живут прямо в
    # сессии — без таблиц подходов. kind: cardio|strength|skill|other. У детальных сессий kind=None.
    kind: str | None = None
    duration_min: float | None = None  # длительность тренировки, мин
    rpe: float | None = None  # субъективное усилие 0–10
    created_at: dt.datetime = Field(default_factory=utcnow)


class StrengthSet(SQLModel, table=True):
    __tablename__ = "strength_set"

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="workout_session.id", index=True)
    exercise_id: int = Field(foreign_key="exercise.id", index=True)
    set_index: int | None = None  # порядковый номер подхода в сессии
    reps: int | None = None
    weight_kg: float | None = None
    rest_sec: float | None = None  # отдых после подхода, сек (S3.4)
    rpe: float | None = None  # субъективная интенсивность (0–10)


class CardioLog(SQLModel, table=True):
    __tablename__ = "cardio_log"

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="workout_session.id", index=True)
    exercise_id: int | None = Field(default=None, foreign_key="exercise.id", index=True)
    distance_km: float | None = None
    duration_sec: float | None = None  # длительность, сек (S3.5)
    avg_hr: int | None = None
    max_hr: int | None = None  # пиковый пульс (S3.5)
    avg_pace: str | None = None  # темп, считается из дистанции/времени, напр. "5:30 /км"


class SkillLog(SQLModel, table=True):
    __tablename__ = "skill_log"

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="workout_session.id", index=True)
    exercise_id: int = Field(foreign_key="exercise.id", index=True)
    attempts: int | None = None  # сколько попыток на элементе (S3.6)
    landed: int | None = None  # сколько удачных приземлений (S3.6)
    hold_sec: float | None = None  # длительность удержания (стойка, планш…)
    reps: int | None = None
    quality: str | None = None  # субъективная оценка / прогресс
    notes: str | None = None


class WorkoutMedia(SQLModel, table=True):
    """Медиа тренировки (S3.11): фото с зала / видео рекорда трюка. Байты не храним — только
    путь к файлу на диске (data/uploads/workouts/), как progress_photo. media_type: image|video
    (по MIME). Несколько медиа на сессию разрешено (по id)."""

    __tablename__ = "workout_media"

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="workout_session.id", index=True)
    media_path: str
    media_type: str  # image | video
    uploaded_at: dt.datetime = Field(default_factory=utcnow)


class PersonalRecord(SQLModel, table=True):
    __tablename__ = "personal_record"

    id: int | None = Field(default=None, primary_key=True)
    exercise_id: int = Field(foreign_key="exercise.id", index=True)
    # тип рекорда (S3.10): max_weight | best_1rm | best_pace | max_distance —
    # дискриминатор, чтобы сравнивать новый результат с лучшим того же рода.
    metric: str = Field(index=True)
    date: dt.date = Field(index=True)
    value: float  # значение рекорда (для темпа — сек/км, меньше = лучше)
    unit: str | None = None  # кг / сек/км / км
    notes: str | None = None
