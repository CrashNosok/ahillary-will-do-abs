"""Личная числовая цель по базовому упражнению: напр. «Жим лёжа → 100 кг».

Привязана к пользователю (user_id) и каталожному упражнению (exercise_id, общий каталог).
Одна цель на пару (user_id, exercise_id) — уникальный индекс. Рисуется целевой линией на
графиках силовых/кардио в «Прогресс» и редактируется в «Мой кабинет».
"""

import datetime as dt

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models._time import utcnow


class ExerciseTarget(SQLModel, table=True):
    __tablename__ = "exercise_target"
    __table_args__ = (
        UniqueConstraint("user_id", "exercise_id", name="uq_exercise_target_user_exercise"),
    )

    id: int | None = Field(default=None, primary_key=True)
    # Владелец цели (M0): изоляция по пользователю. exercise — общий каталог (без user_id).
    user_id: int = Field(foreign_key="user.id", index=True)
    exercise_id: int = Field(foreign_key="exercise.id", index=True)
    target_value: float
    unit: str | None = None  # единица упражнения на момент постановки (кг/км/сек/повторы)
    created_at: dt.datetime = Field(default_factory=utcnow)
