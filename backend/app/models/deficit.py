"""Дневной дефицит калорий (S1.1): deficit = eaten - burn, посчитанный за день."""

import datetime as dt

from sqlmodel import Field, SQLModel

from app.models._time import utcnow


class DeficitDay(SQLModel, table=True):
    __tablename__ = "deficit_day"

    date: dt.date = Field(primary_key=True)  # один расчёт на день
    eaten_kcal: int | None = None
    burn_kcal: int | None = None
    deficit_kcal: int | None = None
    computed_at: dt.datetime = Field(default_factory=utcnow)
