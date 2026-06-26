"""Очистка данных дня/недели с архивацией (clear_category): архивируем + удаляем, скоуп по
пользователю, тренировки тянут медиа, неизвестная категория → ValueError."""

import datetime as dt
import json

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401 — регистрирует таблицы в SQLModel.metadata
from app.models.deleted import DeletedRecord
from app.models.nutrition import FoodEntry
from app.models.workout import WorkoutMedia, WorkoutSession
from app.services.clear import clear_category

DAY = dt.date(2026, 6, 10)
OTHER = dt.date(2026, 6, 11)


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_clear_food_archives_and_deletes(session):
    session.add(FoodEntry(user_id=1, date=DAY, meal="Обед", product_name="x", kcal=100))
    session.add(FoodEntry(user_id=1, date=DAY, meal="Ужин", product_name="y", kcal=200))
    session.add(FoodEntry(user_id=1, date=OTHER, meal="Обед", product_name="z"))
    session.commit()

    assert clear_category(session, user_id=1, category="food", date=DAY) == 2
    assert session.exec(select(FoodEntry).where(FoodEntry.date == DAY)).all() == []
    assert len(session.exec(select(FoodEntry).where(FoodEntry.date == OTHER)).all()) == 1  # другой день цел
    arch = session.exec(
        select(DeletedRecord).where(DeletedRecord.source_table == "food_entry")
    ).all()
    assert len(arch) == 2
    assert json.loads(arch[0].payload)["product_name"] in {"x", "y"}


def test_clear_training_takes_media(session):
    ws = WorkoutSession(user_id=1, date=DAY, title="т")
    session.add(ws)
    session.commit()
    session.add(WorkoutMedia(session_id=ws.id, media_path="/x.jpg", media_type="image"))
    session.commit()

    assert clear_category(session, user_id=1, category="training", date=DAY) == 1
    assert session.exec(select(WorkoutSession)).all() == []
    assert session.exec(select(WorkoutMedia)).all() == []  # медиа ушли вместе с тренировкой
    tables = {r.source_table for r in session.exec(select(DeletedRecord)).all()}
    assert tables == {"workout_session", "workout_media"}


def test_clear_scoped_by_user(session):
    session.add(FoodEntry(user_id=1, date=DAY, meal="О", product_name="a"))
    session.add(FoodEntry(user_id=2, date=DAY, meal="О", product_name="b"))
    session.commit()

    assert clear_category(session, user_id=1, category="food", date=DAY) == 1
    assert len(session.exec(select(FoodEntry).where(FoodEntry.user_id == 2)).all()) == 1  # чужое цело


def test_clear_unknown_category(session):
    with pytest.raises(ValueError):
        clear_category(session, user_id=1, category="bogus", date=DAY)
