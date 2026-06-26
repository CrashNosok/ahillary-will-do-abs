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
from app.services.clear import clear_category, restore_records

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

    assert len(clear_category(session, user_id=1, category="food", date=DAY)) == 2
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

    assert len(clear_category(session, user_id=1, category="training", date=DAY)) == 2  # сессия + медиа
    assert session.exec(select(WorkoutSession)).all() == []
    assert session.exec(select(WorkoutMedia)).all() == []  # медиа ушли вместе с тренировкой
    tables = {r.source_table for r in session.exec(select(DeletedRecord)).all()}
    assert tables == {"workout_session", "workout_media"}


def test_clear_scoped_by_user(session):
    session.add(FoodEntry(user_id=1, date=DAY, meal="О", product_name="a"))
    session.add(FoodEntry(user_id=2, date=DAY, meal="О", product_name="b"))
    session.commit()

    assert len(clear_category(session, user_id=1, category="food", date=DAY)) == 1
    assert len(session.exec(select(FoodEntry).where(FoodEntry.user_id == 2)).all()) == 1  # чужое цело


def test_clear_unknown_category(session):
    with pytest.raises(ValueError):
        clear_category(session, user_id=1, category="bogus", date=DAY)


def test_clear_then_restore_roundtrip(session):
    # тренировка + медиа → очистка → восстановление по id архива возвращает обе строки на место
    ws = WorkoutSession(user_id=1, date=DAY, title="бег")
    session.add(ws)
    session.commit()
    session.add(WorkoutMedia(session_id=ws.id, media_path="/p.mp4", media_type="video"))
    session.commit()

    ids = clear_category(session, user_id=1, category="training", date=DAY)
    assert session.exec(select(WorkoutSession)).all() == []

    assert restore_records(session, user_id=1, ids=ids) == 2
    sessions = session.exec(select(WorkoutSession)).all()
    media = session.exec(select(WorkoutMedia)).all()
    assert len(sessions) == 1 and sessions[0].title == "бег"
    assert len(media) == 1 and media[0].session_id == sessions[0].id  # FK снова сходится
    assert session.exec(select(DeletedRecord)).all() == []  # архив очищен после восстановления


def test_restore_scoped_by_user(session):
    # чужие архивные id восстановить нельзя
    session.add(FoodEntry(user_id=2, date=DAY, meal="О", product_name="b"))
    session.commit()
    ids = clear_category(session, user_id=2, category="food", date=DAY)
    assert restore_records(session, user_id=1, ids=ids) == 0  # user 1 не трогает архив user 2
    assert session.exec(select(FoodEntry).where(FoodEntry.user_id == 2)).all() == []
