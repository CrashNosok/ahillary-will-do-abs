"""Vision-разбор скрина активности Welltory (S1.9).

Скрин «Анализ активности → Дни → выбранный день» — растровая сводка дня (плитки
ккал / шаги / МЕТ / длительности). Структурированного экспорта нет, поэтому поля
извлекает vision-модель (MODEL_VISION), а нормализует их Python: модель делает
только OCR плиток, всю арифметику (часы→минуты, отрезание единиц) детерминированно
делает парсер — так результат не зависит от того, как модель посчитает.

Форматы плиток зафиксированы в docs/sample-formats.md. Контракт надёжности:
- невалидный ответ модели (не JSON-объект) → VisionParseError — контролируемая
  ошибка, а не падение процесса (критерий «невалидный ответ не роняет сервер»);
- отсутствующее, null или нечитаемое значение поля → None (обработка пропусков).

Атрибуты ActivityVision совпадают 1:1 с колонками ActivityDay
(app/models/activity.py): длительности — в минутах, ккал/МЕТ/шаги — целые.
"""

import json
import re
from dataclasses import dataclass

from app.services import llm

# Скрин и плитки русские — промпт тоже русский. Просим строго JSON и только текст
# плиток (без вычислений на стороне модели), ровно восемь ключей карточки S1.9.
ACTIVITY_PROMPT = (
    "На изображении — скриншот экрана «Анализ активности» приложения Welltory "
    "(вкладка «Дни», выбран один день). Внизу экрана — сетка плиток с дневными "
    "показателями. Извлеки значения плиток и верни СТРОГО один JSON-объект и "
    "ничего больше: без markdown, без пояснений, без тройных кавычек.\n"
    "Ровно эти восемь ключей и какие плитки им соответствуют:\n"
    '  "всего_ккал"      — плитка ВСЕГО ККАЛ\n'
    '  "активные_ккал"   — плитка АКТ. ККАЛ\n'
    '  "шаги"            — плитка ШАГИ\n'
    '  "в_движении"      — плитка В ДВИЖЕНИИ\n'
    '  "без_движения"    — плитка БЕЗ ДВИЖ.\n'
    '  "разминка"        — плитка РАЗМИНКА\n'
    '  "активные_мет"    — плитка АКТ. МЕТ\n'
    '  "интенсивные_мет" — плитка ИНТ. МЕТ\n'
    "Значение каждого ключа — текст плитки РОВНО как на экране, строкой: например "
    '"1218 ккал", "4459", "2ч 53м", "7ч", "0 мин", "782 МЕТ". Если плитки нет или '
    "значение не читается — поставь null. Ничего не вычисляй и не переводи единицы "
    "— просто перепиши, что видишь."
)

# Первая группа цифр (с внутренними пробелами-разделителями тысяч): «1218 ккал»,
# «1 218 ккал», «782 МЕТ», «4459».
_INT_RE = re.compile(r"\d[\d\s]*")
# Длительность неконсистентна (docs/sample-formats.md): «2ч 53м» / «7ч» / «0 мин».
# «мин» начинается с «м», поэтому одна регулярка ловит и «53м», и «0 мин».
_HOURS_RE = re.compile(r"(\d+)\s*ч")
_MINUTES_RE = re.compile(r"(\d+)\s*м")


class VisionParseError(ValueError):
    """Ответ vision-модели — не разбираемый JSON-объект."""


@dataclass(frozen=True)
class ActivityVision:
    """Нормализованные показатели дня со скрина Welltory.

    Атрибуты 1:1 с колонками ActivityDay; длительности — в минутах, ккал/МЕТ/шаги
    — целые без единиц. None = плитка отсутствовала или значение не распозналось.
    `raw` — исходный JSON-объект модели (для аудита и колонки ActivityDay.raw_json).
    """

    total_kcal: int | None
    active_kcal: int | None
    steps: int | None
    moving_min: int | None
    idle_min: int | None
    warmup_min: int | None
    active_met: int | None
    intense_met: int | None
    raw: dict


def _parse_int(value: object) -> int | None:
    """«1218 ккал»/«4459»/«782 МЕТ» → 1218/4459/782. None/без цифр/bool → None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    match = _INT_RE.search(str(value))
    if not match:
        return None
    return int(re.sub(r"\s", "", match.group()))


def _parse_duration_min(value: object) -> int | None:
    """«2ч 53м»→173, «7ч»→420, «0 мин»→0. Нет ни ч, ни м (или None) → None."""
    if value is None or isinstance(value, bool):
        return None
    text = str(value)
    hours = _HOURS_RE.search(text)
    minutes = _MINUTES_RE.search(text)
    if hours is None and minutes is None:
        return None
    return (int(hours.group(1)) * 60 if hours else 0) + (int(minutes.group(1)) if minutes else 0)


def _extract_json(text: str) -> dict:
    """Достать JSON-объект из ответа модели.

    Модель иногда оборачивает JSON в ```json … ``` или добавляет прозу — пробуем
    сырой текст, затем подстроку от первой `{` до последней `}`. Не объект → ошибка.
    """
    candidates = [text]
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict):
            return data
    raise VisionParseError(f"ответ модели не содержит JSON-объекта: {text[:200]!r}")


def parse_activity_response(text: str) -> ActivityVision:
    """Текст ответа vision-модели → ActivityVision.

    Невалидный JSON → VisionParseError; отсутствующие/нечитаемые поля → None.
    """
    data = _extract_json(text)
    return ActivityVision(
        total_kcal=_parse_int(data.get("всего_ккал")),
        active_kcal=_parse_int(data.get("активные_ккал")),
        steps=_parse_int(data.get("шаги")),
        moving_min=_parse_duration_min(data.get("в_движении")),
        idle_min=_parse_duration_min(data.get("без_движения")),
        warmup_min=_parse_duration_min(data.get("разминка")),
        active_met=_parse_int(data.get("активные_мет")),
        intense_met=_parse_int(data.get("интенсивные_мет")),
        raw=data,
    )


def parse_activity_screen(image_bytes: bytes, model: str | None = None) -> ActivityVision:
    """Полный путь: vision-запрос по скрину + разбор ответа в ActivityVision.

    Сетевые/API-ошибки приходят как llm.LLMError, невалидный JSON — как
    VisionParseError; оба контролируемы и не роняют сервер.
    """
    reply = llm.vision(image_bytes, ACTIVITY_PROMPT, model=model)
    return parse_activity_response(reply)
