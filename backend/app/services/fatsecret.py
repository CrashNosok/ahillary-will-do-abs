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
import uuid
from dataclasses import dataclass, field

from sqlmodel import Session, select

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


@dataclass(frozen=True)
class Totals:
    """Заявленные/посчитанные нутриенты строки или набора продуктов (None → 0.0)."""

    kcal: float = 0.0
    fat_g: float = 0.0
    carb_g: float = 0.0
    protein_g: float = 0.0


@dataclass
class DiaryImport:
    """Разбор дневника: продукты + заявленные итоги (день и приёмы) для сверки.

    `declared_day` — итог из строки-даты (дублирует «Всего», берём один).
    `declared_meals` — приём → его заявленный итог (включая пустой Перекус/Другое).
    `entries` несут проставленную дату; import_id ставит `import_food_diary`.
    """

    date: dt.date
    entries: list[FoodEntry]
    declared_day: Totals
    declared_meals: dict[str, Totals] = field(default_factory=dict)


def _row_totals(row: list[str]) -> Totals:
    """Нутриенты строки по индексам колонок; пустая ячейка/нет колонки → 0.0."""

    def cell(idx: int) -> float:
        return (parse_decimal(row[idx]) if idx < len(row) else None) or 0.0

    return Totals(cell(_KCAL), cell(_FAT), cell(_CARB), cell(_PROTEIN))


def sum_totals(entries: list[FoodEntry]) -> Totals:
    """Сумма нутриентов по продуктам (None → 0.0)."""
    return Totals(
        kcal=sum(e.kcal or 0.0 for e in entries),
        fat_g=sum(e.fat_g or 0.0 for e in entries),
        carb_g=sum(e.carb_g or 0.0 for e in entries),
        protein_g=sum(e.protein_g or 0.0 for e in entries),
    )


def totals_match(a: Totals, b: Totals, *, tol: float = 1.0) -> bool:
    """Сходятся ли итоги по каждому полю в пределах `tol`.

    FatSecret округляет и сами продукты, и итоги, поэтому сумма продуктов может
    дрейфовать от заявленного итога на доли единицы — допуск 1.0 на поле это
    покрывает. ponytail: общий допуск; если краевые сэмплы дадут больший дрейф —
    поднять tol или масштабировать его от числа продуктов.
    """
    return (
        abs(a.kcal - b.kcal) <= tol
        and abs(a.fat_g - b.fat_g) <= tol
        and abs(a.carb_g - b.carb_g) <= tol
        and abs(a.protein_g - b.protein_g) <= tol
    )


def parse_diary(raw: bytes, filename: str | None = None) -> DiaryImport:
    """Строки FatSecret-CSV → продукты + заявленные итоги дня и приёмов.

    Иерархия по ведущим пробелам col0: 0=день/Всего, 1=приём, 2=продукт,
    3=порция. Порция привязывается к продукту строкой выше. Дата дня берётся из
    строки-даты (уровень 0), при неудаче — из имени файла. Заявленный дневной
    итог берётся из первой строки уровня 0 с числами (строка-дата; «Всего» её
    дублирует — второй раз не учитываем).
    """
    day_date: dt.date | None = None
    declared_day: Totals | None = None
    declared_meals: dict[str, Totals] = {}
    current_meal: str | None = None
    entries: list[FoodEntry] = []
    last_product: FoodEntry | None = None

    for row in decode_fatsecret_csv(raw):
        if not row:
            continue
        level = _leading_spaces(row[0])
        label = row[0].strip()

        if level == 0:
            # строка-дата (дневной итог) или «Всего» (grand-total): дублируют друг
            # друга — берём первую с числами, чтобы не учесть итог дважды. Строку-
            # заголовок («Дата,Кал…») этим и отсекаем: она не дата и не «Всего».
            parsed_date = parse_day_date(label)
            if parsed_date is not None or label == "Всего":
                day_date = day_date or parsed_date
                declared_day = declared_day if declared_day is not None else _row_totals(row)
        elif level == 1:
            current_meal = label
            declared_meals[label] = _row_totals(row)
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
    return DiaryImport(
        date=day_date,
        entries=entries,
        declared_day=declared_day or Totals(),
        declared_meals=declared_meals,
    )


def parse_food_diary(raw: bytes, filename: str | None = None) -> list[FoodEntry]:
    """Только продукты дневника (`FoodEntry`, без id) — тонкая обёртка над parse_diary."""
    return parse_diary(raw, filename).entries


def import_food_diary(
    raw: bytes,
    session: Session,
    *,
    filename: str | None = None,
    import_id: str | None = None,
    replace_day: bool = False,
) -> DiaryImport:
    """Разобрать дневник и записать продукты в food_entry под общим import_id.

    `import_id` связывает строки одного импорта; по умолчанию — свежий uuid, так
    что повторный импорт даёт отдельную партию. После commit у продуктов
    проставлены id. Пустые приёмы (без продуктов) строк не дают. Сверку сумм с
    заявленными итогами оставляем вызывающему (`sum_totals`/`totals_match`).

    `replace_day=True` — идемпотентность по дню: перед записью удаляем прежние
    food_entry той же даты, поэтому повторный импорт того же дня заменяет записи,
    а не дублирует их (критерий приёмки S1.8). По умолчанию False — append.
    """
    parsed = parse_diary(raw, filename)
    if replace_day:
        for stale in session.exec(select(FoodEntry).where(FoodEntry.date == parsed.date)).all():
            session.delete(stale)
    batch_id = import_id or uuid.uuid4().hex
    for entry in parsed.entries:
        entry.import_id = batch_id
        session.add(entry)
    session.commit()
    return parsed
