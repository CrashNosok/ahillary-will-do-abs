"""M0·B12 — Инвариант per-user изоляции на уровне схемы.

Карточка: строки, вставляемые в обход API, обязаны нести ``user_id``; pytest
держим зелёным. Инвариант опирается на то, что ``user_id`` у владельческих
таблиц — NOT NULL: фикстура забыла его проставить → INSERT падает, тест краснеет.

Эти тесты стерегут инвариант — чтобы никто в будущем не «починил» падающую
вставку, сделав ``user_id`` nullable, и тем самым тихо не разрешил бесхозные
строки, которые ломают изоляцию данных по пользователю.
"""

import datetime as dt

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401 — регистрирует все таблицы в SQLModel.metadata
from app.models.nutrition import FoodEntry

# Центральные владельческие таблицы — якорь, чтобы тест не оказался пустым, если
# user_id вдруг исчезнет из метаданных (тогда _owner_tables() станет неполной).
_REQUIRED_OWNER_TABLES = {
    "workout_session",
    "personal_record",
    "body_measurement",
    "inbody_measurement",
    "progress_photo",
    "achievement",
    "activity_day",
    "hr_zones",
    "deficit_day",
    "recommendation",
    "smart_goal",
    "food_entry",
}


def _owner_tables() -> dict:
    """Таблицы с колонкой user_id = принадлежат пользователю."""
    return {t.name: t for t in SQLModel.metadata.tables.values() if "user_id" in t.columns}


def test_owner_tables_cover_required_set():
    # Якорь: каждая центральная владельческая таблица несёт колонку user_id.
    missing = _REQUIRED_OWNER_TABLES - _owner_tables().keys()
    assert not missing, f"таблицы потеряли user_id: {sorted(missing)}"


def test_user_id_is_not_null_on_every_owner_table():
    # Главный инвариант: user_id владельческих таблиц — NOT NULL, поэтому любая
    # прямая вставка обязана его проставить (включая будущие новые таблицы).
    nullable = sorted(
        name for name, table in _owner_tables().items() if table.columns["user_id"].nullable
    )
    assert not nullable, f"user_id должен быть NOT NULL у владельческих таблиц: {nullable}"


def test_direct_insert_without_user_id_is_rejected():
    # Поведенческая страховка: вставка владельческой строки в обход API без
    # user_id обязана падать (NOT NULL), а не создавать бесхозную запись.
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(FoodEntry(date=dt.date(2026, 6, 25), meal="Обед", product_name="x", kcal=100))
        with pytest.raises(IntegrityError):
            session.commit()
