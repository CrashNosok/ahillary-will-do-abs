"""Изоляция данных по пользователям (M0) — регрессия на найденные утечки.

Чужой импорт еды с заменой дня НЕ удаляет еду другого пользователя; дефицит считается только
по своей еде. (Эндпоинты /progress/energy|strength|cardio тоже доскоуплены по user_id.)
"""

import datetime as dt
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401 — регистрирует таблицы в SQLModel.metadata
from app.models import FoodEntry
from app.models.activity import ActivityDay
from app.services.deficit import recompute
from app.services.fatsecret import import_food_diary

_SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "FoodDiary_260620_foods.csv"
DAY = dt.date(2026, 6, 20)


def _session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_import_replace_day_keeps_other_users_food():
    s = _session()
    import_food_diary(_SAMPLE.read_bytes(), s, user_id=1, filename=_SAMPLE.name)
    u1_before = len(s.exec(select(FoodEntry).where(FoodEntry.user_id == 1)).all())
    assert u1_before > 0
    # пользователь 2 импортирует тот же день с заменой — еда пользователя 1 должна уцелеть
    import_food_diary(_SAMPLE.read_bytes(), s, user_id=2, filename=_SAMPLE.name, replace_day=True)
    assert len(s.exec(select(FoodEntry).where(FoodEntry.user_id == 1)).all()) == u1_before
    assert len(s.exec(select(FoodEntry).where(FoodEntry.user_id == 2)).all()) > 0


def test_deficit_uses_only_owner_food():
    s = _session()
    s.add(FoodEntry(user_id=1, date=DAY, meal="О", product_name="a", kcal=1000))
    s.add(FoodEntry(user_id=2, date=DAY, meal="О", product_name="b", kcal=99999))  # чужая еда
    s.add(ActivityDay(user_id=1, date=DAY, total_kcal=2000))
    s.commit()
    d = recompute(DAY, s, user_id=1)
    assert d.eaten_kcal == 1000  # только своя еда (1000), а не чужие 99999 и не сумма 100999
