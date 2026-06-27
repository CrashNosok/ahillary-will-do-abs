"""Реестр метрик-параметров: единый источник правды для целей пользователя.

Каждая вводимая метрика (КРОМЕ роста) — одна запись MetricSpec: канонический ключ
(= колонка БД для тела / дневной ключ), подпись, единица, группа, желаемое направление
и откуда брать значение. Реестр питает форму целей в «Мой кабинет», целевые линии на
графиках «Прогресс» и резолверы прогресса к цели (snapshot + /progress/goal). Зеркало
на фронте — frontend/src/lib/metricRegistry.ts (держать синхронным по ключам).

Канонические ключи целей = имена колонок БД (waist_cm, glutes_cm, …). Историю целей,
писавшую укороченные ключи (hips/waist/chest), перемапливаем через LEGACY_KEY_MAP —
иначе цель молча терялась (hips не маппился на glutes_cm).
"""

import datetime as dt
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func
from sqlmodel import Session, select

from app.models.activity import ActivityDay
from app.models.body import BodyMeasurement, InbodyMeasurement
from app.models.deficit import DeficitDay
from app.models.nutrition import FoodEntry

# Группы метрик (для группировки в форме и на графиках).
GROUP_COMPOSITION = "composition"
GROUP_CIRCUMFERENCE = "circumference"
GROUP_DAILY = "daily"


@dataclass(frozen=True)
class MetricSpec:
    """Описание одной метрики-параметра. model/column заданы для метрик тела (есть ряд
    замеров во времени); у дневных норм model=None и задан daily_source."""

    key: str  # канонический ключ (колонка БД тела / дневной ключ)
    label: str
    unit: str
    group: str
    good_dir: str  # 'up' — рост хорошо; 'down' — снижение хорошо
    model: type | None  # InbodyMeasurement | BodyMeasurement | None (дневные)
    column: str | None  # колонка модели (= key для тела); None для дневных
    daily_source: str | None = None  # 'food' | 'activity' | 'deficit' (только дневные)

    @property
    def is_daily(self) -> bool:
        return self.group == GROUP_DAILY


def _body(key: str, label: str, unit: str, group: str, good_dir: str, model: type) -> MetricSpec:
    """Метрика тела: column == key (канонический ключ = колонка БД)."""
    return MetricSpec(key, label, unit, group, good_dir, model, key)


def _daily(key: str, label: str, unit: str, good_dir: str, source: str) -> MetricSpec:
    """Дневная норма: модели/колонки нет, значение берётся из daily_source."""
    return MetricSpec(key, label, unit, GROUP_DAILY, good_dir, None, None, source)


# Состав тела (InbodyMeasurement) — вес идёт первым (он же отдельная колонка цели легаси).
_COMPOSITION = (
    _body("weight_kg", "Вес", "кг", GROUP_COMPOSITION, "down", InbodyMeasurement),
    _body("body_fat_pct", "Процент жира", "%", GROUP_COMPOSITION, "down", InbodyMeasurement),
    _body("muscle_mass_kg", "Мышечная масса", "кг", GROUP_COMPOSITION, "up", InbodyMeasurement),
    _body("visceral_fat", "Висцеральный жир", "ур.", GROUP_COMPOSITION, "down", InbodyMeasurement),
    _body("water", "Вода", "л", GROUP_COMPOSITION, "up", InbodyMeasurement),
)

# Обхваты (BodyMeasurement) — рост (height_cm) НЕ цель, в реестр не входит.
# calf_*_cm в UI подписаны как «Бедро» (так пожелал пользователь).
_CIRCUMFERENCE = (
    _body("waist_cm", "Талия", "см", GROUP_CIRCUMFERENCE, "down", BodyMeasurement),
    _body("belly_cm", "Живот", "см", GROUP_CIRCUMFERENCE, "down", BodyMeasurement),
    _body("chest_cm", "Грудь", "см", GROUP_CIRCUMFERENCE, "up", BodyMeasurement),
    _body("shoulders_cm", "Плечи", "см", GROUP_CIRCUMFERENCE, "up", BodyMeasurement),
    _body("biceps_l_cm", "Бицепс Л", "см", GROUP_CIRCUMFERENCE, "up", BodyMeasurement),
    _body("biceps_r_cm", "Бицепс П", "см", GROUP_CIRCUMFERENCE, "up", BodyMeasurement),
    _body("glutes_cm", "Ягодицы", "см", GROUP_CIRCUMFERENCE, "up", BodyMeasurement),
    _body("calf_l_cm", "Бедро Л", "см", GROUP_CIRCUMFERENCE, "up", BodyMeasurement),
    _body("calf_r_cm", "Бедро П", "см", GROUP_CIRCUMFERENCE, "up", BodyMeasurement),
)

# Дневные нормы — у них нет траектории baseline→target; сравниваются со средним за период.
# kcal_in/fat/carb — это потолок (меньше = лучше); белок/шаги/дефицит — больше = лучше.
_DAILY = (
    _daily("kcal_in", "Калории (съедено)", "ккал/день", "down", "food"),
    _daily("protein_g", "Белки", "г/день", "up", "food"),
    _daily("fat_g", "Жиры", "г/день", "down", "food"),
    _daily("carb_g", "Углеводы", "г/день", "down", "food"),
    _daily("steps", "Шаги", "шаг/день", "up", "activity"),
    _daily("deficit_kcal", "Дефицит", "ккал/день", "up", "deficit"),
)

REGISTRY: tuple[MetricSpec, ...] = (*_COMPOSITION, *_CIRCUMFERENCE, *_DAILY)
BY_KEY: dict[str, MetricSpec] = {m.key: m for m in REGISTRY}


def resolve_metric(key: str) -> MetricSpec | None:
    """Спецификация метрики по каноническому ключу или None (неизвестный ключ)."""
    return BY_KEY.get(key)


def metrics_by_group(group: str) -> tuple[MetricSpec, ...]:
    """Метрики одной группы в порядке реестра."""
    return tuple(m for m in REGISTRY if m.group == group)


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def effective_targets(goal: Any) -> dict[str, float]:
    """Единая карта {канонический_ключ: цель} активной цели из target_metrics_json.

    Оставляем только известные реестру ключи и валидные числа (бэкенд их и так валидирует
    при сохранении). Легаси-колонки целей удалены — единственный источник target_metrics_json.
    """
    out: dict[str, float] = {}
    for raw_key, raw_val in (getattr(goal, "target_metrics_json", None) or {}).items():
        val = _to_float(raw_val)
        if raw_key in BY_KEY and val is not None:
            out[raw_key] = val
    return out


# «Текущие показатели» для префилла целей: тело — последний не-null замер за окно;
# дневные нормы — среднее за окно (один день — выброс, среднее ближе к «обычному дню»).
CURRENT_BODY_WINDOW_DAYS = 180
CURRENT_DAILY_WINDOW_DAYS = 30


def _avg(values: list[Any]) -> float | None:
    """Среднее по не-null числам (1 знак); пусто → None (метрику не показываем)."""
    nums = [float(v) for v in values if v is not None]
    return round(sum(nums) / len(nums), 1) if nums else None


def _latest_body_values(
    session: Session, model: type, today: dt.date, user_id: int
) -> dict[str, float]:
    """{колонка реестра: последнее не-null значение} замеров владельца за окно тела.

    ponytail: тянем строки окна и берём первый не-null сверху (свежие первыми) — O(n) по
    скану в памяти, n мал (личный трекер); индексный max-per-column не нужен.
    """
    start = today - dt.timedelta(days=CURRENT_BODY_WINDOW_DAYS - 1)
    rows = session.exec(
        select(model)
        .where(model.user_id == user_id, model.date >= start, model.date <= today)
        .order_by(model.date.desc(), model.id.desc())
    ).all()
    out: dict[str, float] = {}
    for spec in REGISTRY:
        if spec.model is not model or spec.column is None:
            continue
        for row in rows:
            value = getattr(row, spec.column)
            if value is not None:
                out[spec.key] = round(float(value), 1)
                break
    return out


def _current_daily_values(session: Session, today: dt.date, user_id: int) -> dict[str, float]:
    """Среднесуточные «текущие» дневные нормы за окно (только метрики с данными)."""
    start = today - dt.timedelta(days=CURRENT_DAILY_WINDOW_DAYS - 1)
    food = session.exec(
        select(
            func.sum(FoodEntry.kcal),
            func.sum(FoodEntry.protein_g),
            func.sum(FoodEntry.fat_g),
            func.sum(FoodEntry.carb_g),
        )
        .where(FoodEntry.user_id == user_id, FoodEntry.date >= start, FoodEntry.date <= today)
        .group_by(FoodEntry.date)
    ).all()
    steps = session.exec(
        select(ActivityDay.steps).where(
            ActivityDay.user_id == user_id, ActivityDay.date >= start, ActivityDay.date <= today
        )
    ).all()
    deficit = session.exec(
        select(DeficitDay.deficit_kcal).where(
            DeficitDay.user_id == user_id,
            DeficitDay.date >= start,
            DeficitDay.date <= today,
            DeficitDay.deficit_kcal.is_not(None),
        )
    ).all()
    candidates = {
        "kcal_in": _avg([r[0] for r in food]),
        "protein_g": _avg([r[1] for r in food]),
        "fat_g": _avg([r[2] for r in food]),
        "carb_g": _avg([r[3] for r in food]),
        "steps": _avg(steps),  # одноколоночный select → список скаляров (не кортежей)
        "deficit_kcal": _avg(deficit),
    }
    return {k: v for k, v in candidates.items() if v is not None}


def current_metric_values(
    session: Session, *, user_id: int, today: dt.date | None = None
) -> dict[str, float]:
    """{ключ_реестра: текущее значение} владельца — дефолт для формы целей.

    Тело — последний не-null замер за окно; дневные нормы — среднее за окно. Метрика без
    данных в карту не попадает (форма оставит поле пустым). Ключи = ключи реестра.
    """
    today = today or dt.date.today()
    out: dict[str, float] = {}
    out.update(_latest_body_values(session, InbodyMeasurement, today, user_id))
    out.update(_latest_body_values(session, BodyMeasurement, today, user_id))
    out.update(_current_daily_values(session, today, user_id))
    return out
