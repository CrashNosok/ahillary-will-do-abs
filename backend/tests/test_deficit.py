"""Расчёт дневного дефицита (S1.12): eaten − burn, статус неполного дня, пересчёт.

Закрывает критерии карточки:
- на 2026-06-20 deficit = 3250 − всего_ккал(Welltory) (assert);
- при отсутствии одного источника — статус «неполный день», без ложного нуля;
плюс: пересчёт при изменении еды/активности и идемпотентность по дню.
"""

import datetime as dt
from pathlib import Path

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401 — регистрирует таблицы в SQLModel.metadata
from app.models.activity import ActivityDay
from app.models.deficit import STATUS_COMPLETE, STATUS_INCOMPLETE, DeficitDay
from app.models.nutrition import FoodEntry
from app.services import deficit
from app.services.fatsecret import import_food_diary

DAY = dt.date(2026, 6, 20)
BURN = 600  # всего_ккал(Welltory) для проверки assert
_SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "FoodDiary_260620_foods.csv"


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _add_food(session: Session, date: dt.date, *kcals: float | None) -> None:
    for k in kcals:
        session.add(FoodEntry(user_id=1, date=date, meal="Обед", product_name="x", kcal=k))
    session.commit()


def test_deficit_is_eaten_minus_burn(session):
    # критерий: на 2026-06-20 deficit = 3250 − всего_ккал(Welltory)
    _add_food(session, DAY, 455.0, 1000.0, 1795.0)  # сумма 3250
    session.add(ActivityDay(user_id=1, date=DAY, total_kcal=BURN))
    session.commit()

    row = deficit.recompute(DAY, session, 1)
    assert row.eaten_kcal == 3250
    assert row.burn_kcal == BURN
    assert row.deficit_kcal == 3250 - BURN
    assert row.status == STATUS_COMPLETE


def test_missing_activity_is_incomplete_without_false_zero(session):
    # критерий: нет источника активности → «неполный день», deficit не 0, а None
    _add_food(session, DAY, 3250.0)
    row = deficit.recompute(DAY, session, 1)
    assert row.eaten_kcal == 3250
    assert row.burn_kcal is None
    assert row.deficit_kcal is None  # без ложного нуля
    assert row.status == STATUS_INCOMPLETE


def test_missing_food_is_incomplete_without_false_zero(session):
    # критерий: нет источника еды → «неполный день», deficit None
    session.add(ActivityDay(user_id=1, date=DAY, total_kcal=BURN))
    session.commit()
    row = deficit.recompute(DAY, session, 1)
    assert row.eaten_kcal is None
    assert row.burn_kcal == BURN
    assert row.deficit_kcal is None
    assert row.status == STATUS_INCOMPLETE


def test_zero_kcal_entries_are_not_a_missing_source(session):
    # записи есть, но ккал по ним 0 → eaten=0 (валидный ноль, не пропуск источника)
    _add_food(session, DAY, 0.0, None)
    session.add(ActivityDay(user_id=1, date=DAY, total_kcal=BURN))
    session.commit()
    row = deficit.recompute(DAY, session, 1)
    assert row.eaten_kcal == 0
    assert row.deficit_kcal == -BURN
    assert row.status == STATUS_COMPLETE


def test_recompute_is_idempotent_upsert(session):
    _add_food(session, DAY, 1000.0)
    session.add(ActivityDay(user_id=1, date=DAY, total_kcal=400))
    session.commit()
    deficit.recompute(DAY, session, 1)

    _add_food(session, DAY, 250.0)  # еда поменялась → новый пересчёт
    row = deficit.recompute(DAY, session, 1)
    assert row.eaten_kcal == 1250
    assert row.deficit_kcal == 1250 - 400
    assert len(session.exec(select(DeficitDay)).all()) == 1  # один день — одна запись


def test_food_import_triggers_recompute(session):
    # пересчёт при изменении еды: импорт сэмпла сам пишет deficit_day (eaten=3250)
    import_food_diary(
        _SAMPLE.read_bytes(), session, user_id=1, filename=_SAMPLE.name, replace_day=True
    )
    row = session.get(DeficitDay, (1, DAY))  # составной PK (user_id, date)
    assert row is not None
    assert row.eaten_kcal == 3250
    assert row.status == STATUS_INCOMPLETE  # активности ещё нет → неполный день


def test_activity_save_triggers_recompute(session, tmp_path, monkeypatch):
    # пересчёт при изменении активности: сохранение дня Welltory пишет deficit_day
    from app.core import db
    from app.services import welltory

    monkeypatch.setattr(db, "welltory_dir", lambda: tmp_path)
    _add_food(session, DAY, 3250.0)
    welltory.save_activity_day_values(
        b"\x89PNG fake", DAY, session, user_id=1, fields={"total_kcal": BURN}, raw={}
    )
    row = session.get(DeficitDay, (1, DAY))  # составной PK (user_id, date)
    assert row is not None
    assert row.burn_kcal == BURN
    assert row.deficit_kcal == 3250 - BURN
    assert row.status == STATUS_COMPLETE
