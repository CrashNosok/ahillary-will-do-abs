"""Тренировки (S1.2): сессия и её записи по упражнениям + персональные рекорды.

workout_session — одна тренировка (FK sport_id). Внутри сессии лежат записи разных
типов, каждая ссылается на session (FK session_id) и на упражнение (FK exercise_id):
- strength_set — силовой подход (вес/повторы/RPE);
- cardio_log — кардио (дистанция/время/пульс);
- skill_log — навык (удержание/повторы, напр. стойка, планш).
personal_record — лучший результат по упражнению (FK exercise_id), вне сессии.
"""

import datetime as dt

from sqlmodel import Field, SQLModel

from app.models._time import utcnow


class WorkoutSession(SQLModel, table=True):
    __tablename__ = "workout_session"

    id: int | None = Field(default=None, primary_key=True)
    sport_id: int | None = Field(default=None, foreign_key="sport.id", index=True)
    date: dt.date = Field(index=True)
    title: str | None = None
    notes: str | None = None
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
    duration_min: float | None = None
    avg_hr: int | None = None
    avg_pace: str | None = None  # темп, напр. "5:30 /км"


class SkillLog(SQLModel, table=True):
    __tablename__ = "skill_log"

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="workout_session.id", index=True)
    exercise_id: int = Field(foreign_key="exercise.id", index=True)
    hold_sec: float | None = None  # длительность удержания (стойка, планш…)
    reps: int | None = None
    quality: str | None = None  # субъективная оценка / прогресс
    notes: str | None = None


class PersonalRecord(SQLModel, table=True):
    __tablename__ = "personal_record"

    id: int | None = Field(default=None, primary_key=True)
    exercise_id: int = Field(foreign_key="exercise.id", index=True)
    date: dt.date = Field(index=True)
    value: float  # значение рекорда
    unit: str | None = None  # кг / повторы / сек / км
    notes: str | None = None
