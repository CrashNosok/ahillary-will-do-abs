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


def test_user_profile_fields_have_defaults():
    # критерий M0·B2: доп. поля профиля с дефолтами (display_name пусто, is_active=True)
    from app.models.user import User

    user = User(email="x@example.com", password_hash="h")
    assert user.display_name is None
    assert user.is_active is True


def test_json_column_roundtrips_dict():
    engine = _memory_engine()
    payload = {"всего_ккал": 1218, "tiles": {"steps": 4459}}
    with Session(engine) as session:
        session.add(ActivityDay(date=date(2026, 6, 20), raw_json=payload))
        session.commit()
    with Session(engine) as session:
        row = session.exec(select(ActivityDay)).one()
    assert row.raw_json == payload  # dict сериализуется/читается через JSON-колонку


# --- S1.2: тренировки + LLM + ачивки ---

_S12_TABLES = {
    "sport",
    "exercise",
    "workout_session",
    "strength_set",
    "cardio_log",
    "skill_log",
    "personal_record",
    "recommendation",
    "achievement",
    "achievement_proof",
}

# (таблица, колонка) -> таблица, на которую FK обязан ссылаться. Критерий приёмки:
# FK на sport/exercise/session согласованы.
_EXPECTED_FKS = {
    ("exercise", "sport_id"): "sport",
    ("workout_session", "sport_id"): "sport",
    ("workout_session", "activity_date"): "activity_day",  # связь с Welltory-днём (S3.9)
    ("strength_set", "session_id"): "workout_session",
    ("strength_set", "exercise_id"): "exercise",
    ("cardio_log", "session_id"): "workout_session",
    ("cardio_log", "exercise_id"): "exercise",
    ("skill_log", "session_id"): "workout_session",
    ("skill_log", "exercise_id"): "exercise",
    ("personal_record", "exercise_id"): "exercise",
    ("achievement", "sport_id"): "sport",
    ("achievement_proof", "achievement_id"): "achievement",
    ("recommendation", "goal_id"): "smart_goal",
}


def test_create_all_builds_every_s12_table():
    tables = set(inspect(_memory_engine()).get_table_names())
    assert _S12_TABLES <= tables  # критерий: все таблицы создаются


def test_foreign_keys_reference_expected_tables():
    # критерий: FK на sport/exercise/session (и др.) согласованы
    insp = inspect(_memory_engine())
    actual = {
        (table, col): fk["referred_table"]
        for table in _S12_TABLES
        for fk in insp.get_foreign_keys(table)
        for col in fk["constrained_columns"]
    }
    assert actual == _EXPECTED_FKS
