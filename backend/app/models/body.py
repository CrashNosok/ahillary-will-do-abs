"""Замеры тела (S1.1).

body_measurement — ручные обхваты в см (парные — левый/правый) + рост и заметки.
inbody_measurement — данные весов/InBody: вес, %жира, мышцы и гибкий metrics_json.
progress_photo — фото прогресса тела: путь к файлу на диске + дата + заметка.
"""

import datetime as dt
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.models._time import utcnow


class BodyMeasurement(SQLModel, table=True):
    __tablename__ = "body_measurement"

    id: int | None = Field(default=None, primary_key=True)
    date: dt.date = Field(index=True)
    height_cm: float | None = None
    waist_cm: float | None = None
    belly_cm: float | None = None
    calf_l_cm: float | None = None
    calf_r_cm: float | None = None
    chest_cm: float | None = None
    shoulders_cm: float | None = None
    biceps_l_cm: float | None = None
    biceps_r_cm: float | None = None
    glutes_cm: float | None = None
    notes: str | None = None


class InbodyMeasurement(SQLModel, table=True):
    __tablename__ = "inbody_measurement"

    id: int | None = Field(default=None, primary_key=True)
    date: dt.date = Field(index=True)
    weight_kg: float | None = None
    body_fat_pct: float | None = None
    muscle_mass_kg: float | None = None
    visceral_fat: float | None = None
    water: float | None = None
    metrics_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    source_image_path: str | None = None
    parsed_at: dt.datetime = Field(default_factory=utcnow)


class ProgressPhoto(SQLModel, table=True):
    """Фото прогресса тела. Байты не храним — только путь к файлу на диске.

    Несколько фото на одну дату разрешены (по id). Файлы лежат в
    data/uploads/progress/, путь относительно BACKEND_DIR.
    """

    __tablename__ = "progress_photo"

    id: int | None = Field(default=None, primary_key=True)
    date: dt.date = Field(index=True)
    source_image_path: str
    notes: str | None = None
    uploaded_at: dt.datetime = Field(default_factory=utcnow)
