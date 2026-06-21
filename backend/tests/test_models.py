"""Модели ядра + ингеста (S1.1): create_all поднимает все таблицы, гибкие поля — JSON."""

from datetime import date

from sqlalchemy import JSON, inspect
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401 — импорт регистрирует таблицы в SQLModel.metadata
from app.models import ActivityDay, HrZones, InbodyMeasurement

# Имена таблиц из карточки (snake_case заданы через __tablename__, иначе было бы "foodentry").
_EXPECTED_TABLES = {
    "user",
    "smart_goal",
    "food_entry",
    "activity_day",
    "hr_zones",
    "deficit_day",
    "body_measurement",
    "inbody_measurement",
}


def _memory_engine():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return engine


def test_create_all_builds_every_core_table():
    tables = set(inspect(_memory_engine()).get_table_names())
    assert _EXPECTED_TABLES <= tables  # критерий: таблицы создаются через create_all


def test_flexible_fields_are_json_columns():
    # критерий: гибкие raw/metrics-поля — JSON-колонки
    assert isinstance(ActivityDay.__table__.c.raw_json.type, JSON)
    assert isinstance(HrZones.__table__.c.zones_json.type, JSON)
    assert isinstance(InbodyMeasurement.__table__.c.metrics_json.type, JSON)


def test_json_column_roundtrips_dict():
    engine = _memory_engine()
    payload = {"всего_ккал": 1218, "tiles": {"steps": 4459}}
    with Session(engine) as session:
        session.add(ActivityDay(date=date(2026, 6, 20), raw_json=payload))
        session.commit()
    with Session(engine) as session:
        row = session.exec(select(ActivityDay)).one()
    assert row.raw_json == payload  # dict сериализуется/читается через JSON-колонку
