"""Декодирование экспорта дневника питания FatSecret (S1.5).

Первый шаг парсера: из сырых байт `.csv` получить строки данных, очищенные от
служебного обвеса. Формат зафиксирован в docs/sample-formats.md.

Почему декодирование — отдельный шаг (а не просто `csv.reader`):
- BOM (`EF BB BF`) снимается через `utf-8-sig`, иначе первый `#` склеится с BOM;
- переводы строк CRLF нормализуются (`splitlines`);
- строки-комментарии (начинаются с `#`) отбрасываются ДО csv-парсинга — внутри
  них есть запятые и кавычки (`# Report,"суббота, ..."`), наивный csv-ридер не
  отличил бы их от данных;
- `csv.reader` учитывает закавыченные поля (RU-дата и десятичные с запятой);
- `skipinitialspace` НЕ используется: ведущие пробелы первой ячейки задают
  иерархию (приём / продукт / порция) и значимы.
"""

import csv
import datetime as dt
import re

from app.models.nutrition import FoodEntry

# Колонки нутриентов по индексу (docs/sample-formats.md). Матчим по позиции, а не
# по русскому заголовку с нестабильными пробелами.
_KCAL, _FAT, _CARB, _PROTEIN = 1, 2, 4, 7

# RU-месяцы в родительном падеже («июня», не «июнь») → номер месяца.
_RU_MONTHS = {
    name: idx
    for idx, name in enumerate(
        (
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
        ),
        start=1,
    )
}

# «суббота, июня 20, 2026» → месяц(слово) число, год.
_DAY_DATE_RE = re.compile(r"([а-яё]+)\s+(\d{1,2}),\s*(\d{4})", re.IGNORECASE)
# FoodDiary_260620_foods.csv → YYMMDD.
_FILENAME_DATE_RE = re.compile(r"_(\d{2})(\d{2})(\d{2})_")
# Ведущее число порции: «300 г», «1,5 г».
_PORTION_NUM_RE = re.compile(r"[\d.,]+")


def decode_fatsecret_csv(raw: bytes) -> list[list[str]]:
    """Строки данных FatSecret-CSV (без комментариев и пустых строк).

    `raw` — сырые байты файла (как из загрузки). Строка-заголовок колонок
    остаётся в выдаче: это данные, а не комментарий. Разбор колонок и иерархии —
    следующие шаги парсера, здесь только декодирование.
    """
    text = raw.decode("utf-8-sig")
    lines = [line for line in text.splitlines() if line.strip() and not line.startswith("#")]
    return list(csv.reader(lines))


def parse_decimal(value: str) -> float | None:
    """«170,4» → 170.4, «3250» → 3250.0, пусто → None.

    Десятичные во FatSecret — с запятой-разделителем (поле в кавычках). csv-ридер
    уже снимает кавычки; `strip('"')` оставлен защитно на случай прямого вызова.
    """
    cleaned = value.strip().strip('"').replace(",", ".")
    if not cleaned:
        return None
    return float(cleaned)


def parse_day_date(text: str) -> dt.date | None:
    """«суббота, июня 20, 2026» → date(2026, 6, 20). Не распознано → None."""
    match = _DAY_DATE_RE.search(text)
    if not match:
        return None
    month = _RU_MONTHS.get(match.group(1).lower())
    if month is None:
        return None
    return dt.date(int(match.group(3)), month, int(match.group(2)))


def day_date_from_filename(name: str) -> dt.date | None:
    """Fallback: FoodDiary_260620_foods.csv → date(2026, 6, 20). YY → 2000+YY."""
    match = _FILENAME_DATE_RE.search(name)
    if not match:
        return None
    yy, mm, dd = (int(g) for g in match.groups())
    return dt.date(2000 + yy, mm, dd)


def _leading_spaces(cell: str) -> int:
    """Глубина иерархии = число ведущих литеральных пробелов первой ячейки."""
    return len(cell) - len(cell.lstrip(" "))


def _portion_grams(raw: str) -> float | None:
    """«300 г» → 300.0. Ведущее число порции (единица в сэмпле всегда «г»)."""
    match = _PORTION_NUM_RE.search(raw)
    return parse_decimal(match.group()) if match else None


def parse_food_diary(raw: bytes, filename: str | None = None) -> list[FoodEntry]:
    """Строки FatSecret-CSV → список съеденных продуктов (`FoodEntry`, без id).

    Иерархия по ведущим пробелам col0: 0=день/Всего, 1=приём, 2=продукт,
    3=порция. Порция привязывается к продукту строкой выше. Дата дня берётся из
    строки-даты (уровень 0), при неудаче — из имени файла. `FoodEntry` не
    кладётся в БД: import_id/persist — следующий шаг.
    """
    day_date: dt.date | None = None
    current_meal: str | None = None
    entries: list[FoodEntry] = []
    last_product: FoodEntry | None = None

    for row in decode_fatsecret_csv(raw):
        if not row:
            continue
        level = _leading_spaces(row[0])
        label = row[0].strip()

        if level == 0:
            # строка-дата (дневной итог) или «Всего» (grand-total) — продукты не несут
            day_date = day_date or parse_day_date(label)
        elif level == 1:
            current_meal = label
        elif level == 2:
            last_product = FoodEntry(
                date=dt.date.min,  # проставится после цикла, когда дата известна
                meal=current_meal or "",
                product_name=label,
                kcal=parse_decimal(row[_KCAL]),
                fat_g=parse_decimal(row[_FAT]),
                carb_g=parse_decimal(row[_CARB]),
                protein_g=parse_decimal(row[_PROTEIN]),
            )
            entries.append(last_product)
        elif level == 3 and last_product is not None:
            last_product.portion_raw = label
            last_product.portion_grams = _portion_grams(label)

    if day_date is None and filename:
        day_date = day_date_from_filename(filename)
    if day_date is None:
        raise ValueError("дату дня не удалось получить ни из отчёта, ни из имени файла")

    for entry in entries:
        entry.date = day_date
    return entries
