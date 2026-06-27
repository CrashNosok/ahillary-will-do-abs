"""SMART-цель пользователя (S1.3): сквозная сущность цели.

Цели по параметрам хранятся единой картой target_metrics_json {ключ_реестра: значение}
(services/metrics.py) — состав тела, обхваты и дневные нормы; плюс start_date, deadline,
baseline_json, why_notes, status. Гибкие карты — JSON-колонки (структура нестабильна).
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
    # Владелец цели (M0·B5): изоляция данных по пользователю. NOT NULL + FK на user.id.
    user_id: int = Field(foreign_key="user.id", index=True)
    # Единая карта целей {канонический_ключ: значение} по реестру метрик (services/metrics.py):
    # состав тела + обхваты + дневные нормы. Единственный источник правды для целевых линий и
    # рекомендаций (легаси-колонки target_weight_kg/…/measurements удалены — миграция перенесла
    # их сюда).
    target_metrics_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    start_date: dt.date | None = None
    deadline: dt.date | None = None
    baseline_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    why_notes: str | None = None
    status: str = Field(default=GoalStatus.active, index=True)
    created_at: dt.datetime = Field(default_factory=utcnow)
