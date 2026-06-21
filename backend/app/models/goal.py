"""SMART-цель пользователя (S1.3): сквозная сущность цели.

Поля заданы карточкой S1.3: target_weight_kg, target_body_fat_pct,
target_measurements_json, start_date, deadline, baseline_json, why_notes, status.
Гибкие замеры/база — JSON-колонки (структура нестабильна, без миграций).
Активной считается ровно одна цель (status == "active"); архивная — "archived".
Имя таблицы и id PK сохранены: на smart_goal.id ссылается recommendation.goal_id.
"""

import datetime as dt
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.models._time import utcnow


class GoalStatus(StrEnum):
    active = "active"
    archived = "archived"


class SmartGoal(SQLModel, table=True):
    __tablename__ = "smart_goal"

    id: int | None = Field(default=None, primary_key=True)
    target_weight_kg: float | None = None
    target_body_fat_pct: float | None = None
    target_measurements_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    start_date: dt.date | None = None
    deadline: dt.date | None = None
    baseline_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    why_notes: str | None = None
    status: str = Field(default=GoalStatus.active, index=True)
    created_at: dt.datetime = Field(default_factory=utcnow)
