"""Vision-разбор скрина InBody с гибкой схемой (S2.10).

Скрин InBody (стационарный анализатор или умные весы) — растровая сводка состава
тела. Набор показателей у разных аппаратов/весов различается, поэтому схема гибкая:
vision-модель (MODEL_VISION) возвращает ВСЕ показатели, что видит, а Python
раскладывает их детерминированно. Пять ключевых показателей (вес, %жира, мыш.масса,
висцеральный жир, вода) едут в типизированные колонки InbodyMeasurement, всё
остальное — в гибкий metrics_json «как есть» (карточка: «неизвестные поля
сохраняются в metrics_json»).

Контракт надёжности (как у welltory-парсера):
- невалидный ответ модели (не JSON-объект) → InbodyParseError — контролируемая
  ошибка, а не падение процесса;
- отсутствующее, null или нечитаемое значение ключевого поля → None.

Карточка просит только парсер. Сохранение замера + загрузку скрина (роут/UI)
делает отдельная карточка — InbodyMeasurement уже хранит source_image_path/parsed_at.
"""

import datetime as dt
import json
import re
from dataclasses import dataclass
from typing import Any

from sqlmodel import Session, select

from app.core import db
from app.models._time import utcnow
from app.models.body import InbodyMeasurement
from app.services import llm

# Скрин InBody бывает русским и английским, поэтому в промпте называем показатели на
# обоих языках. Просим строго JSON: пять ключевых ключей канонично + все прочие
# показатели в тот же объект (это и есть «гибкая схема»).
INBODY_PROMPT = (
    "На изображении — скриншот результатов биоимпедансного анализа состава тела "
    "(InBody, умные весы и т.п.). Набор показателей у разных аппаратов различается. "
    "Извлеки ВСЕ показатели, что видишь, и верни СТРОГО один JSON-объект и ничего "
    "больше: без markdown, без пояснений, без тройных кавычек.\n"
    "Для пяти ключевых показателей используй РОВНО эти ключи (независимо от языка "
    "на экране):\n"
    '  "вес"              — вес тела (Weight)\n'
    '  "процент_жира"     — процент жира (Percent Body Fat / PBF / Body Fat %)\n'
    '  "мышечная_масса"   — мышечная/скелетно-мышечная масса (Muscle Mass / SMM)\n'
    '  "висцеральный_жир" — висцеральный жир (Visceral Fat Level / Area)\n'
    '  "вода"             — общая вода тела (Total Body Water)\n'
    "ВСЕ остальные показатели (BMI, белок, минералы, костная масса, базовый обмен/"
    "BMR, метаболический возраст, балл и т.п.) тоже включи в тот же объект, используя "
    "название показателя с экрана как ключ.\n"
    "Значение каждого ключа — текст РОВНО как на экране, строкой, с единицами: "
    'например "75.3 kg", "18.2 %", "32.1", "8", "45.6 L". Если показателя нет или он '
    "не читается — поставь null. Ничего не вычисляй и не переводи единицы."
)

# Канонические ключи пяти ключевых показателей → колонки InbodyMeasurement.
# Порядок сохранён для читаемости; всё, чего тут нет, уходит в metrics_json.
_KEY_FIELDS = {
    "вес": "weight_kg",
    "процент_жира": "body_fat_pct",
    "мышечная_масса": "muscle_mass_kg",
    "висцеральный_жир": "visceral_fat",
    "вода": "water",
}

# Первое число с необязательной дробной частью: «75.3 kg», «18,2 %», «8», «45.6 L».
# ponytail: разделитель тысяч не поддержан — у веса/жира/мышц/воды тысяч не бывает.
_FLOAT_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


class InbodyParseError(ValueError):
    """Ответ vision-модели — не разбираемый JSON-объект."""


@dataclass(frozen=True)
class InbodyVision:
    """Разобранный скрин InBody.

    Пять ключевых показателей — типизированные float (None = поля нет / не читается).
    `metrics_json` — все прочие показатели как вернула модель (гибкая схема).
    `raw` — полный JSON-объект модели (для аудита и InbodyMeasurement).
    """

    weight_kg: float | None
    body_fat_pct: float | None
    muscle_mass_kg: float | None
    visceral_fat: float | None
    water: float | None
    metrics_json: dict[str, Any]
    raw: dict[str, Any]


def _parse_float(value: object) -> float | None:
    """«75.3 kg»/«18,2 %»/«8» → 75.3/18.2/8.0. None/без цифр/bool → None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = _FLOAT_RE.search(str(value))
    if not match:
        return None
    return float(match.group().replace(",", "."))


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
    raise InbodyParseError(f"ответ модели не содержит JSON-объекта: {text[:200]!r}")


def parse_inbody_response(text: str) -> InbodyVision:
    """Текст ответа vision-модели → InbodyVision.

    Невалидный JSON → InbodyParseError; ключевые поля → float|None; всё остальное →
    metrics_json «как есть».
    """
    data = _extract_json(text)
    key_values = {column: _parse_float(data.get(key)) for key, column in _KEY_FIELDS.items()}
    metrics_json = {key: value for key, value in data.items() if key not in _KEY_FIELDS}
    return InbodyVision(metrics_json=metrics_json, raw=data, **key_values)


def parse_inbody_screen(image_bytes: bytes, model: str | None = None) -> InbodyVision:
    """Полный путь: vision-запрос по скрину InBody + разбор ответа в InbodyVision.

    Сетевые/API-ошибки приходят как llm.LLMError, невалидный JSON — как
    InbodyParseError; оба контролируемы и не роняют сервер.
    """
    reply = llm.vision(image_bytes, INBODY_PROMPT, model=model)
    return parse_inbody_response(reply)


# Колонки InbodyMeasurement из пяти ключевых показателей (промо-колонки карточки
# S2.11). Совпадают 1:1 с полями InbodyVision; всё прочее живёт в metrics_json.
KEY_FIELD_NAMES = (
    "weight_kg",
    "body_fat_pct",
    "muscle_mass_kg",
    "visceral_fat",
    "water",
)


def _upsert_measurement(
    image_bytes: bytes,
    date: dt.date,
    session: Session,
    *,
    user_id: int,
    fields: dict[str, float | None],
    metrics_json: dict[str, Any],
) -> InbodyMeasurement:
    """Записать скрин на диск и upsert-нуть замер с готовыми значениями (S2.11).

    Файл кладётся в `data/uploads/inbody/<date>.png`, замер пишется в
    `inbody_measurement`: пять промо-колонок + гибкий metrics_json + source_image_path
    + parsed_at. Идемпотентно по дню — путь `<date>.png` подразумевает один скрин на
    дату, поэтому повторная загрузка того же дня заменяет запись и перезаписывает файл.
    """
    dest = db.inbody_dir() / f"{date}.png"
    dest.write_bytes(image_bytes)
    try:
        source_image_path = str(dest.relative_to(db.BACKEND_DIR))
    except ValueError:  # каталог данных вне backend/ (абсолютный DATA_DIR) — храним как есть
        source_image_path = str(dest)

    existing = session.exec(select(InbodyMeasurement).where(InbodyMeasurement.date == date)).first()
    measurement = existing or InbodyMeasurement(date=date, user_id=user_id)
    for name in KEY_FIELD_NAMES:
        setattr(measurement, name, fields.get(name))
    measurement.metrics_json = metrics_json
    measurement.source_image_path = source_image_path
    measurement.parsed_at = utcnow()
    session.add(measurement)
    session.commit()
    session.refresh(measurement)
    return measurement


def save_inbody_measurement(
    image_bytes: bytes,
    date: dt.date,
    session: Session,
    *,
    user_id: int,
    model: str | None = None,
) -> InbodyMeasurement:
    """Разобрать скрин InBody и сохранить замер + исходник (S2.11).

    Полный путь: vision-разбор → файл `data/uploads/inbody/<date>.png` → upsert
    InbodyMeasurement. Разбор идёт ПЕРВЫМ: при ошибке файл не пишется и записи нет.
    InbodyParseError / llm.LLMError пробрасываются как есть — HTTP-код выбирает роут.
    """
    vision = parse_inbody_screen(image_bytes, model=model)
    fields = {name: getattr(vision, name) for name in KEY_FIELD_NAMES}
    return _upsert_measurement(
        image_bytes, date, session, user_id=user_id, fields=fields, metrics_json=vision.metrics_json
    )


def save_inbody_values(
    image_bytes: bytes,
    date: dt.date,
    session: Session,
    *,
    user_id: int,
    fields: dict[str, float | None],
    metrics_json: dict[str, Any],
) -> InbodyMeasurement:
    """Сохранить замер с уже выверенными пользователем значениями (S2.11).

    vision НЕ дёргается: пять промо-полей приходят с экрана сверки (пользователь
    подтвердил/поправил их), а metrics_json — прочие показатели из шага превью.
    """
    return _upsert_measurement(
        image_bytes, date, session, user_id=user_id, fields=fields, metrics_json=metrics_json
    )
