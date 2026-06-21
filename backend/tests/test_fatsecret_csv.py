"""Декодирование FatSecret-CSV (S1.5): BOM/CRLF, отсев комментариев, кавычки.

Гоняем на реальном сэмпле samples/FoodDiary_260620_foods.csv плюс синтетические
байты для краевых случаев. Проверяем именно ШАГ ДЕКОДИРОВАНИЯ — отделение данных
от служебных строк, не разбор колонок (это следующий шаг парсера).
"""

from pathlib import Path

from app.services.fatsecret import decode_fatsecret_csv

# samples/ лежит в корне репозитория (backend/tests/ → parents[2]).
_SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "FoodDiary_260620_foods.csv"


def _sample_rows() -> list[list[str]]:
    return decode_fatsecret_csv(_SAMPLE.read_bytes())


def test_comments_and_empty_lines_are_dropped():
    # критерий: данные отделены от комментариев
    rows = _sample_rows()
    assert rows, "должны вернуться строки данных"
    assert all(row for row in rows), "пустых строк быть не должно"
    assert all(not row[0].startswith("#") for row in rows), "строки-# отфильтрованы"
    # 1 заголовок + 20 строк дневника (см. сэмпл) = 21 строка данных.
    assert len(rows) == 21


def test_header_and_known_rows_present():
    rows = _sample_rows()
    header = rows[0]
    assert header[0] == "Дата"
    assert len(header) == 11  # Дата + 10 нутриентных колонок
    first_cells = [row[0] for row in rows]
    assert " Завтрак" in first_cells  # приём пищи — один ведущий пробел
    assert "Всего" in first_cells  # grand-total идёт строкой данных, не комментарием


def test_quoted_comma_fields_are_not_split():
    # критерий: поля с запятой в кавычках не ломают разбор
    rows = _sample_rows()
    day_row = next(r for r in rows if r[0].startswith("суббота"))
    # RU-дата с двумя запятыми внутри — одна ячейка, не три.
    assert day_row[0] == "суббота, июня 20, 2026"
    # Десятичное "170,4" — одна ячейка с запятой внутри.
    assert day_row[1] == "3250"
    assert day_row[2] == "170,4"


def test_bom_is_stripped():
    rows = _sample_rows()
    assert "﻿" not in rows[0][0]
    assert rows[0][0] == "Дата"


def test_leading_spaces_drive_hierarchy_are_preserved():
    # критерий: НЕ используем skipinitialspace — ведущие пробелы значимы
    rows = _sample_rows()
    first_cells = [row[0] for row in rows]
    meal = next(c for c in first_cells if c.strip() == "Завтрак")
    product = next(c for c in first_cells if "Квас" in c)
    portion = next(c for c in first_cells if c.strip() == "300 г")
    assert meal == " Завтрак"  # уровень 1 — один пробел
    assert product.startswith("  ") and not product.startswith("   ")  # уровень 2
    assert portion == "   300 г"  # уровень 3 — три пробела, единственная ячейка


def test_handles_bom_crlf_and_inline_comment_commas():
    # Синтетика: комментарий с запятыми/кавычками не должен утечь в данные.
    raw = (
        b"\xef\xbb\xbf"  # BOM
        b'# Report,"a, b",c\r\n'  # комментарий с запятыми и кавычками
        b"\r\n"  # пустая строка
        b"Header,X\r\n"
        b' Meal,"1,5"\r\n'
    )
    rows = decode_fatsecret_csv(raw)
    assert rows == [["Header", "X"], [" Meal", "1,5"]]
