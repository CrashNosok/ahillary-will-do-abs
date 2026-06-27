"""Разбор FatSecret-CSV (S1.6): иерархия день/приём/продукт/порция + числа + дата.

Шаг после декодирования (S1.5): из строк данных собрать продукты с привязанной
порцией, распарсенными десятичными и датой дня. Гоняем на реальном сэмпле
samples/FoodDiary_260620_foods.csv плюс синтетика для краёв (fallback даты).
"""

import datetime as dt
from pathlib import Path

import pytest

from app.services.fatsecret import (
    day_date_from_filename,
    parse_day_date,
    parse_decimal,
    parse_food_diary,
)

_SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "FoodDiary_260620_foods.csv"


def _entries():
    return parse_food_diary(_SAMPLE.read_bytes(), filename=_SAMPLE.name)


# --- десятичные --------------------------------------------------------------


def test_parse_decimal_comma_to_float():
    # критерий приёмки: '170,4' -> 170.4
    assert parse_decimal("170,4") == 170.4


def test_parse_decimal_integer_without_separator():
    assert parse_decimal("3250") == 3250.0


def test_parse_decimal_strips_stray_quotes():
    # защитно: даже если кавычки не сняты csv-ридером
    assert parse_decimal('"6,6"') == 6.6


def test_parse_decimal_empty_is_none():
    assert parse_decimal("") is None
    assert parse_decimal("   ") is None


# --- дата дня ----------------------------------------------------------------


def test_parse_day_date_ru_genitive():
    # критерий приёмки: дата = 2026-06-20
    assert parse_day_date("суббота, июня 20, 2026") == dt.date(2026, 6, 20)


def test_parse_day_date_all_genitive_months():
    months = [
        "января",
        "февраля",
        "марта",
        "апреля",
        "мая",
        "июня",
        "июля",
        "августа",
        "сентября",
        "октября",
        "ноября",
        "декабря",
    ]
    for idx, name in enumerate(months, start=1):
        assert parse_day_date(f"вторник, {name} 5, 2026") == dt.date(2026, idx, 5)


def test_parse_day_date_unparseable_is_none():
    assert parse_day_date("Всего") is None


def test_day_date_from_filename_yymmdd():
    # fallback: FoodDiary_260620_foods.csv -> 2026-06-20
    assert day_date_from_filename("FoodDiary_260620_foods.csv") == dt.date(2026, 6, 20)


def test_day_date_from_filename_no_match_is_none():
    assert day_date_from_filename("notes.txt") is None


# --- иерархия и привязка порции ----------------------------------------------


def test_only_products_returned():
    # уровень 2 (продукты): Квас, Шарлотка, Кесадилья, Брускетт, Тунцом, Попкорн, Крылышки
    entries = _entries()
    assert len(entries) == 7


def test_day_date_attached_to_every_entry():
    assert all(e.date == dt.date(2026, 6, 20) for e in _entries())


def test_portion_attaches_to_product_above():
    # критерий приёмки: '300 г' привязана к 'Зеленая Линия Квас'
    kvas = next(e for e in _entries() if "Квас" in e.product_name)
    assert kvas.portion_raw == "300 г"
    assert kvas.portion_grams == 300.0


def test_meal_attribution():
    by_name = {e.product_name.strip(): e for e in _entries()}
    assert by_name["Зеленая Линия  Квас"].meal == "Завтрак"
    assert by_name["Здрасте Кесадилья с Курицей"].meal == "Обед"
    assert by_name["Ростик'c - KFC Крылышки Острые"].meal == "Ужин"


def test_nutrients_mapped_by_index():
    # маппинг kcal=1, fat=2, carb=4, protein=7 (docs/sample-formats.md)
    kvas = next(e for e in _entries() if "Квас" in e.product_name)
    assert kvas.kcal == 96.0
    assert kvas.fat_g == 0.0
    assert kvas.carb_g == 24.0
    assert kvas.protein_g == 0.0


def test_decimal_nutrient_on_product():
    # '6,6' -> 6.6 на реальном продукте
    sharlotka = next(e for e in _entries() if "Шарлотка" in e.product_name)
    assert sharlotka.fat_g == 6.6


def test_extended_nutrients_empty_on_sample():
    # В сэмпле Клетч/Сахар/Н·жир пусты (',,') → None (детали появятся, когда экспорт их несёт)
    kvas = next(e for e in _entries() if "Квас" in e.product_name)
    assert kvas.fiber_g is None
    assert kvas.sugar_g is None
    assert kvas.saturated_fat_g is None


def test_extended_nutrients_parsed_when_present():
    # Полная строка: satfat=col3, fiber=col5, sugar=col6 — читаются по индексам
    raw = b"Header,X\r\n  Product,200,10,3,40,5,8,15,,,\r\n   100 g\r\n"
    e = parse_food_diary(raw, filename="FoodDiary_260620_foods.csv")[0]
    assert (e.kcal, e.fat_g, e.carb_g, e.protein_g) == (200.0, 10.0, 40.0, 15.0)
    assert e.saturated_fat_g == 3.0
    assert e.fiber_g == 5.0
    assert e.sugar_g == 8.0


def test_short_row_legacy_csv_no_index_error():
    # Старый короткий экспорт (обрывается до новых колонок) → новые поля None, без IndexError
    raw = b"Header,X\r\n  Product,200,10\r\n   100 g\r\n"
    e = parse_food_diary(raw, filename="FoodDiary_260620_foods.csv")[0]
    assert e.kcal == 200.0 and e.fat_g == 10.0
    assert e.carb_g is None and e.protein_g is None
    assert e.fiber_g is None and e.sugar_g is None and e.saturated_fat_g is None


def test_empty_meal_has_no_products():
    # ' Перекус/Другое,,,,,,,,,,' — приём без продуктов, в выдаче его нет
    assert not any(e.meal == "Перекус/Другое" for e in _entries())


# --- fallback даты из имени файла --------------------------------------------


def test_date_fallback_to_filename_when_row_unparseable():
    # строка дня без распознаваемой даты -> берём дату из имени файла
    raw = b"Header,X\r\nObed,,,,,,,,,,\r\n  Product A,10,0,,5,,,2,,,\r\n   100 g\r\n"
    entries = parse_food_diary(raw, filename="FoodDiary_260620_foods.csv")
    assert len(entries) == 1
    assert entries[0].date == dt.date(2026, 6, 20)


def test_missing_date_everywhere_raises():
    raw = b"Header,X\r\n  Product A,10,0,,5,,,2,,,\r\n"
    with pytest.raises(ValueError):
        parse_food_diary(raw, filename=None)
