"""SMART-цель пользователя (S1.1).

Карточка не задала поля smart_goal — берём разумный дефолт по схеме SMART:
Specific (title/notes), Measurable (целевые вес/талия/дефицит), Time-bound (target_date).
Активная цель помечается is_active; история прошлых целей не запрещена.
"""

from datetime import date, datetime

from sqlmodel import Field, SQLModel

from app.models._time import utcnow


class SmartGoal(SQLModel, table=True):
    __tablename__ = "smart_goal"

    id: int | None = Field(default=None, primary_key=True)
    title: str  # Specific — формулировка цели
    target_weight_kg: float | None = None  # Measurable
    target_waist_cm: float | None = None
    daily_deficit_kcal: int | None = None  # целевой дневной дефицит (ср. deficit_day)
    target_date: date | None = None  # Time-bound
    is_active: bool = True
    notes: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
