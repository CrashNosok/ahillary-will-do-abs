"""Vision-разбор скрина Welltory «Анализ тренировки» (ядро экрана 9671).

Экран — растровая сводка одной тренировки: график пульса (AVG/MAX) + плитки ВРЕМЯ/ВСЕГО ккал/
АКТИВ. ккал/ВСЕГО МЕТ/ПОЛЕЗНЫЕ МЕТ/НАГРУЗКА + оценка. Структурного экспорта нет → vision-модель
делает OCR, арифметику (ч→мин, знак %) детерминированно делает Python. Контракт надёжности — как
у разбора активности (welltory.py): не-JSON ответ → VisionParseError (не роняет сервер),
отсутствующее/нечитаемое поле → None. Поля TrainingVision 1:1 с метрик-колонками WorkoutSession.
"""

import re
from dataclasses import dataclass

from app.services import llm
from app.services.welltory import (
    VisionParseError,  # noqa: F401 — реэкспорт, чтобы роут ловил из одного модуля
    _extract_json,
    _parse_duration_min,
    _parse_int,
)

TRAINING_PROMPT = (
    "На изображении — скриншот экрана «Анализ тренировки» приложения Welltory (одна "
    "тренировка). Вверху — график пульса с подписями AVG и MAX; ниже — плитки показателей. "
    "Извлеки значения и верни СТРОГО один JSON-объект и ничего больше: без markdown, без "
    "пояснений, без тройных кавычек.\n"
    "Ровно эти девять ключей и какие элементы им соответствуют:\n"
    '  "время"          — плитка ВРЕМЯ (напр. "1 ч 5 мин")\n'
    '  "всего_ккал"     — плитка ВСЕГО ККАЛ\n'
    '  "активные_ккал"  — плитка АКТИВ. ККАЛ\n'
    '  "всего_мет"      — плитка ВСЕГО МЕТ\n'
    '  "полезные_мет"   — плитка ПОЛЕЗНЫЕ (значение в МЕТ)\n'
    '  "пульс_средний"  — число рядом с AVG на графике пульса\n'
    '  "пульс_макс"     — число рядом с MAX на графике пульса\n'
    '  "нагрузка"       — плитка НАГРУЗКА (напр. "-8%")\n'
    '  "оценка"         — число в кружке оценки (напр. 3)\n'
    "Значение каждого ключа — текст РОВНО как на экране, строкой. Если элемента нет или "
    "значение не читается — поставь null. Ничего не вычисляй и не переводи единицы."
)

# Процент нагрузки может быть отрицательным: «-8%», «−8 %» (юникод-минус).
_PCT_RE = re.compile(r"-?\d+")


def _parse_pct(value: object) -> int | None:
    """«-8%»→-8, «12 %»→12. None/без цифр/bool → None. Сохраняет знак (в отличие от _parse_int)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    m = _PCT_RE.search(str(value).replace("−", "-"))  # − → -
    return int(m.group()) if m else None


@dataclass(frozen=True)
class TrainingVision:
    """Метрики тренировки со скрина (1:1 с колонками WorkoutSession). None = не распознано."""

    duration_min: int | None
    total_kcal: int | None
    active_kcal: int | None
    total_met: int | None
    useful_met: int | None
    hr_avg: int | None
    hr_max: int | None
    load_pct: int | None
    score: int | None
    raw: dict


def parse_training_response(text: str) -> TrainingVision:
    """Текст ответа vision-модели → TrainingVision. Невалидный JSON → VisionParseError."""
    data = _extract_json(text)
    return TrainingVision(
        duration_min=_parse_duration_min(data.get("время")),
        total_kcal=_parse_int(data.get("всего_ккал")),
        active_kcal=_parse_int(data.get("активные_ккал")),
        total_met=_parse_int(data.get("всего_мет")),
        useful_met=_parse_int(data.get("полезные_мет")),
        hr_avg=_parse_int(data.get("пульс_средний")),
        hr_max=_parse_int(data.get("пульс_макс")),
        load_pct=_parse_pct(data.get("нагрузка")),
        score=_parse_int(data.get("оценка")),
        raw=data,
    )


def parse_training_screen(image_bytes: bytes, model: str | None = None) -> TrainingVision:
    """Полный путь: vision-запрос по скрину + разбор в TrainingVision. Ошибки llm.LLMError/
    VisionParseError пробрасываются (HTTP-код выбирает роут)."""
    reply = llm.vision(image_bytes, TRAINING_PROMPT, model=model)
    return parse_training_response(reply)


# Поля метрик WorkoutSession, которые заполняет распознавание/ручной ввод (ядро 9671).
FIELD_NAMES = (
    "duration_min",
    "total_kcal",
    "active_kcal",
    "total_met",
    "useful_met",
    "hr_avg",
    "hr_max",
    "load_pct",
    "score",
)
