"""Дневная активность и пульсовые зоны (S1.1).

activity_day — агрегаты за день со скрина Welltory (см. docs/sample-formats.md):
ккал, шаги, длительности (минуты), МЕТ + сырой raw_json и путь к исходному скрину.
hr_zones — пульсовые зоны за день в гибком zones_json.
Длительности храним в минутах (moving/idle/warmup_min); парсер «2ч 53м» → 173.
"""

import datetime as dt
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.models._time import utcnow


class ActivityDay(SQLModel, table=True):
    __tablename__ = "activity_day"

    date: dt.date = Field(primary_key=True)  # один агрегат на день
    total_kcal: int | None = None
    active_kcal: int | None = None
    steps: int | None = None
    moving_min: int | None = None
    idle_min: int | None = None
    warmup_min: int | None = None
    active_met: int | None = None
    intense_met: int | None = None
    raw_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    source_image_path: str | None = None
    parsed_at: dt.datetime = Field(default_factory=utcnow)


class HrZones(SQLModel, table=True):
    __tablename__ = "hr_zones"

    id: int | None = Field(default=None, primary_key=True)
    # Владелец записи (M0·B4): изоляция данных по пользователю. NOT NULL + FK на user.id.
    user_id: int = Field(foreign_key="user.id", index=True)
    date: dt.date = Field(index=True)
    zones_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    source_image_path: str | None = None
