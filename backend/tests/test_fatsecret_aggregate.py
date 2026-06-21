"""Агрегаты и запись FatSecret-CSV (S1.7): итоги дня/приёмов + persist food_entry.

Шаг после разбора иерархии (S1.6): из распарсенных продуктов собрать дневной и
приёмные итоги, сверить с заявленными в отчёте числами («Всего»/итог дня, итоги
приёмов) и записать продукты в food_entry под общим import_id. Гоняем на реальном
сэмпле samples/FoodDiary_260620_foods.csv плюс in-memory SQLite для записи.
"""

import datetime as dt
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401 — импорт регистрирует таблицы в SQLModel.metadata
from app.models import FoodEntry
from app.services.fatsecret import (
    Totals,
    import_food_diary,
    parse_diary,
    sum_totals,
    totals_match,
)

_SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "FoodDiary_260620_foods.csv"


def _raw() -> bytes:
    return _SAMPLE.read_bytes()


def _memory_session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


# --- заявленные итоги дня -----------------------------------------------------


def test_declared_day_total():
    # критерий приёмки: день 2026-06-20 — 3250 ккал, белки 138.45
    parsed = parse_diary(_raw(), filename=_SAMPLE.name)
    assert parsed.date == dt.date(2026, 6, 20)
    assert parsed.declared_day == Totals(kcal=3250.0, fat_g=170.4, carb_g=274.9, protein_g=138.45)


def test_product_sum_matches_day_total():
    # критерий приёмки: сумма продуктов сходится с итогом дня (в пределах округления)
    parsed = parse_diary(_raw(), filename=_SAMPLE.name)
    computed = sum_totals(parsed.entries)
    assert computed.kcal == 3250.0
    assert computed.protein_g == 138.45
    assert totals_match(computed, parsed.declared_day)


# --- итоги приёмов ------------------------------------------------------------


def test_meals_split_with_declared_totals():
    # критерий приёмки: приёмы Завтрак/Обед/Ужин разнесены
    parsed = parse_diary(_raw(), filename=_SAMPLE.name)
    assert set(parsed.declared_meals) >= {"Завтрак", "Обед", "Ужин"}
    assert parsed.declared_meals["Завтрак"].kcal == 455.0


def test_meal_product_sum_matches_meal_total():
    # сумма продуктов приёма сходится с заявленным итогом приёма
    parsed = parse_diary(_raw(), filename=_SAMPLE.name)
    for meal in ("Завтрак", "Обед", "Ужин"):
        products = [e for e in parsed.entries if e.meal == meal]
        assert totals_match(sum_totals(products), parsed.declared_meals[meal])


def test_empty_meal_has_zero_total_and_no_products():
    # ' Перекус/Другое,,,,,,,,,,' — пустой приём: нулевой итог и без продуктов
    parsed = parse_diary(_raw(), filename=_SAMPLE.name)
    assert parsed.declared_meals["Перекус/Другое"] == Totals()
    assert not any(e.meal == "Перекус/Другое" for e in parsed.entries)


# --- сверка (totals_match) ----------------------------------------------------


def test_totals_match_within_rounding_tolerance():
    a = Totals(kcal=3250.0, protein_g=138.45)
    b = Totals(kcal=3250.4, protein_g=138.0)
    assert totals_match(a, b)  # дрейф ≤ 1 на поле — в пределах округления
    assert not totals_match(a, Totals(kcal=3260.0, protein_g=138.45))  # 10 ккал — мимо


# --- запись в БД --------------------------------------------------------------


def test_import_persists_products_with_shared_import_id():
    session = _memory_session()
    import_food_diary(_raw(), session, filename=_SAMPLE.name)
    rows = session.exec(select(FoodEntry)).all()
    assert len(rows) == 7  # 7 продуктов записаны (пустой приём не даёт строк)
    import_ids = {r.import_id for r in rows}
    assert len(import_ids) == 1 and None not in import_ids  # один import_id на импорт
    assert all(r.id is not None for r in rows)  # PK проставлен после commit
    assert all(r.date == dt.date(2026, 6, 20) for r in rows)


def test_import_uses_provided_import_id():
    session = _memory_session()
    import_food_diary(_raw(), session, filename=_SAMPLE.name, import_id="imp-123")
    rows = session.exec(select(FoodEntry)).all()
    assert {r.import_id for r in rows} == {"imp-123"}


def test_two_imports_get_distinct_ids():
    session = _memory_session()
    import_food_diary(_raw(), session, filename=_SAMPLE.name)
    import_food_diary(_raw(), session, filename=_SAMPLE.name)
    rows = session.exec(select(FoodEntry)).all()
    assert len(rows) == 14
    assert len({r.import_id for r in rows}) == 2  # каждый импорт — свой id
