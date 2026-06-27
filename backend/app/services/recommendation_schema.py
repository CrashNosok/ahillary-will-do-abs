"""Структурированная схема рекомендаций (S4.3): машиночитаемый план еды + тренировок.

Карточка просит строгую JSON-схему ответа модели: план питания (калории / макросы /
приёмы пищи) и план тренировок (упражнения, подходы, повторы, рабочие веса, недельная
прогрессия), увязанные между собой, плюс валидацию — невалидный ответ модели
ОТБРАКОВЫВАЕТСЯ и при необходимости РЕТРАИТСЯ.

Связка «еда ↔ тренировка» зашита в саму схему, а не держится на честном слове модели:
- питание задаётся раздельно для тренировочного дня и дня отдыха (`DayType`);
- число тренировок в неделю обязано совпадать с длиной расписания, дни нумеруются 1..N;
- кросс-проверка двух планов (`RecommendationPlan`): калорий в тренировочный день не
  меньше, чем в день отдыха (нагрузке нужно топливо).
Любой рассинхрон между планами ловится на этапе валидации (`model_validator`), а не в
рантайме потребителя.

Схема строгая: ``extra="forbid"`` — лишний ключ в ответе модели = отбраковка.

Публичное API:
- ``RecommendationPlan`` — корневая Pydantic-модель ответа;
- ``PLAN_EXAMPLE`` — валидный эталонный пример (образец для промпта и фикстура тестов);
- ``plan_json_schema()`` — JSON-схема (Draft) корневой модели;
- ``parse_plan(raw)`` — распарсить+провалидировать JSON-текст ответа модели
  (``InvalidPlanError`` на битом JSON или нарушении схемы);
- ``generate_valid_plan(produce, attempts)`` — звать генератор сырого ответа и
  валидировать; отбраковку ретраить до ``attempts`` раз.
"""

import json
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    model_validator,
)


class _Strict(BaseModel):
    """Базовая модель схемы: лишние ключи запрещены (строгая отбраковка ответа модели)."""

    model_config = ConfigDict(extra="forbid")


class DayType(StrEnum):
    """Тип дня в плане питания — связывает рацион с наличием тренировки."""

    training = "training"
    rest = "rest"


class Macros(_Strict):
    """Макронутриенты в граммах. Ноль допустим, отрицательное — нет."""

    protein_g: float = Field(ge=0)
    carbs_g: float = Field(ge=0)
    fat_g: float = Field(ge=0)


class Meal(_Strict):
    """Один приём пищи: название + калорийность + макросы."""

    name: str = Field(min_length=1)
    calories: float = Field(gt=0)
    macros: Macros


class DayNutrition(_Strict):
    """Рацион одного типа дня: суточные калории/макросы и список приёмов пищи."""

    day_type: DayType
    calories: float = Field(gt=0)
    macros: Macros
    meals: list[Meal] = Field(min_length=1)


class MealPlan(_Strict):
    """План питания: раздельно для тренировочного дня и дня отдыха (это и есть увязка)."""

    training_day: DayNutrition
    rest_day: DayNutrition
    notes: str | None = None

    @model_validator(mode="after")
    def _day_types_consistent(self) -> "MealPlan":
        if self.training_day.day_type is not DayType.training:
            raise ValueError("training_day.day_type должен быть 'training'")
        if self.rest_day.day_type is not DayType.rest:
            raise ValueError("rest_day.day_type должен быть 'rest'")
        return self


class ExercisePrescription(_Strict):
    """Упражнение: подходы, повторы и рабочий вес (null — собственный вес/кардио)."""

    name: str = Field(min_length=1)
    sets: int = Field(ge=1)
    reps: int = Field(ge=1)
    working_weight_kg: float | None = Field(default=None, ge=0)


class WorkoutDay(_Strict):
    """Одна тренировка недели: порядковый номер, фокус и упражнения."""

    day: int = Field(ge=1)  # порядковый номер тренировки в неделе (1..days_per_week)
    focus: str = Field(min_length=1)
    exercises: list[ExercisePrescription] = Field(min_length=1)


class WeekProgression(_Strict):
    """Шаг недельной прогрессии: что изменить относительно прошлой недели."""

    week: int = Field(ge=1)
    adjustment: str = Field(min_length=1)


class WorkoutPlan(_Strict):
    """План тренировок: расписание недели + недельная прогрессия."""

    days_per_week: int = Field(ge=1, le=7)
    schedule: list[WorkoutDay] = Field(min_length=1)
    weekly_progression: list[WeekProgression] = Field(min_length=1)

    @model_validator(mode="after")
    def _schedule_and_progression_consistent(self) -> "WorkoutPlan":
        if len(self.schedule) != self.days_per_week:
            raise ValueError("длина schedule должна совпадать с days_per_week")
        if [d.day for d in self.schedule] != list(range(1, self.days_per_week + 1)):
            raise ValueError("дни schedule должны нумероваться 1..days_per_week без пропусков")
        weeks = [w.week for w in self.weekly_progression]
        if weeks != list(range(1, len(weeks) + 1)):
            raise ValueError("недели прогрессии должны нумероваться 1..N без пропусков")
        return self


class CarbQualityTarget(_Strict):
    """Оценка текущего состояния + целевой ориентир по одному аспекту качества рациона."""

    assessment: str = Field(min_length=1)  # что сейчас (по средним из снапшота)
    target: str = Field(min_length=1)  # к чему стремиться


class NutritionAnalysis(_Strict):
    """Детальный разбор качества рациона (не только калории/макросы): углеводы, клетчатка,
    сахар, насыщенные жиры, качество белка. Модель рассуждает по средним из снапшота
    (avg_carb_g / avg_fiber_g / avg_sugar_g / avg_complex_carb_g и т.д.)."""

    fiber_g_target: float = Field(ge=0)  # целевая клетчатка, г/сут
    sugar_g_limit: float = Field(ge=0)  # потолок добавленного сахара, г/сут
    saturated_fat_g_limit: float = Field(ge=0)  # потолок насыщенных жиров, г/сут
    complex_vs_simple_carbs: CarbQualityTarget  # сложные vs простые углеводы
    fiber: CarbQualityTarget
    sugar: CarbQualityTarget
    saturated_fat: CarbQualityTarget
    protein_quality: CarbQualityTarget  # источники/распределение белка
    summary: str = Field(min_length=1)  # короткий вывод по качеству рациона


class Citation(_Strict):
    """Ссылка на исследование из корпуса. `id` ОБЯЗАН существовать в research/studies.json —
    иначе валидатор отбракует ответ (защита от выдуманных источников)."""

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    authors: list[str] = Field(min_length=1)
    year: int = Field(ge=1900, le=2100)
    url_or_doi: str = Field(min_length=1)
    claim: str = Field(min_length=1)  # какое утверждение отчёта подкрепляет


class RecommendationPlan(_Strict):
    """Корневой структурированный ответ: план еды + тренировок + детальный нутриент-разбор
    + большой доказательный отчёт (markdown) со ссылками на исследования."""

    meal_plan: MealPlan
    workout_plan: WorkoutPlan
    sync_note: str = Field(min_length=1)  # как рацион увязан с тренировками
    nutrition_analysis: NutritionAnalysis
    # Длинный markdown-отчёт секциями; каждое утверждение цитирует работы инлайн как [id].
    evidence_narrative: str = Field(min_length=400)
    citations: list[Citation] = Field(min_length=3)  # ≥3 пристёгнутых исследования

    @model_validator(mode="after")
    def _plans_linked(self) -> "RecommendationPlan":
        # Увязка двух планов: тренировочному дню нужно топливо — его калорийность не
        # может быть ниже дня отдыха. Проверяемое правило связи, а не текст в sync_note.
        if self.meal_plan.training_day.calories < self.meal_plan.rest_day.calories:
            raise ValueError("калорийность тренировочного дня не может быть ниже дня отдыха")
        return self

    @model_validator(mode="after")
    def _citations_exist_in_corpus(self, info: ValidationInfo) -> "RecommendationPlan":
        # Контекст несёт валидные id корпуса (см. parse_plan). Нет контекста — юнит-тест схемы
        # или ре-валидация старой записи — проверку существования пропускаем (структуру всё
        # равно проверили). Это и есть защита от галлюцинированных ссылок при генерации.
        valid_ids = (info.context or {}).get("valid_citation_ids")
        if valid_ids is None:
            return self
        unknown = sorted({c.id for c in self.citations} - set(valid_ids))
        if unknown:
            raise ValueError(f"цитаты ссылаются на отсутствующие в корпусе исследования: {unknown}")
        return self


class InvalidPlanError(ValueError):
    """Ответ модели отбракован: битый JSON или несоответствие схеме плана."""


# Валидный эталонный пример: образец формы для промпта и фикстура для тестов схемы.
PLAN_EXAMPLE: dict[str, Any] = {
    "meal_plan": {
        "training_day": {
            "day_type": "training",
            "calories": 2400,
            "macros": {"protein_g": 170, "carbs_g": 280, "fat_g": 70},
            "meals": [
                {
                    "name": "Завтрак",
                    "calories": 700,
                    "macros": {"protein_g": 45, "carbs_g": 80, "fat_g": 22},
                },
                {
                    "name": "Обед (до тренировки)",
                    "calories": 900,
                    "macros": {"protein_g": 60, "carbs_g": 110, "fat_g": 24},
                },
                {
                    "name": "Ужин (после тренировки)",
                    "calories": 800,
                    "macros": {"protein_g": 65, "carbs_g": 90, "fat_g": 24},
                },
            ],
        },
        "rest_day": {
            "day_type": "rest",
            "calories": 2100,
            "macros": {"protein_g": 170, "carbs_g": 200, "fat_g": 75},
            "meals": [
                {
                    "name": "Завтрак",
                    "calories": 650,
                    "macros": {"protein_g": 45, "carbs_g": 55, "fat_g": 25},
                },
                {
                    "name": "Обед",
                    "calories": 800,
                    "macros": {"protein_g": 65, "carbs_g": 75, "fat_g": 27},
                },
                {
                    "name": "Ужин",
                    "calories": 650,
                    "macros": {"protein_g": 60, "carbs_g": 70, "fat_g": 23},
                },
            ],
        },
        "notes": "В дни силовой добавляй углеводы вокруг тренировки.",
    },
    "workout_plan": {
        "days_per_week": 3,
        "schedule": [
            {
                "day": 1,
                "focus": "Низ тела",
                "exercises": [
                    {"name": "Присед со штангой", "sets": 4, "reps": 6, "working_weight_kg": 80},
                    {"name": "Румынская тяга", "sets": 3, "reps": 8, "working_weight_kg": 70},
                    {"name": "Планка", "sets": 3, "reps": 30, "working_weight_kg": None},
                ],
            },
            {
                "day": 2,
                "focus": "Верх (жим)",
                "exercises": [
                    {"name": "Жим лёжа", "sets": 4, "reps": 6, "working_weight_kg": 60},
                    {"name": "Жим стоя", "sets": 3, "reps": 8, "working_weight_kg": 35},
                    {
                        "name": "Отжимания на брусьях",
                        "sets": 3,
                        "reps": 10,
                        "working_weight_kg": None,
                    },
                ],
            },
            {
                "day": 3,
                "focus": "Верх (тяга)",
                "exercises": [
                    {"name": "Подтягивания", "sets": 4, "reps": 6, "working_weight_kg": None},
                    {"name": "Тяга в наклоне", "sets": 3, "reps": 8, "working_weight_kg": 55},
                ],
            },
        ],
        "weekly_progression": [
            {"week": 1, "adjustment": "Базовые рабочие веса, освоить технику."},
            {"week": 2, "adjustment": "+2.5 кг к приседу и жиму лёжа, остальное без изменений."},
            {"week": 3, "adjustment": "+2.5 кг к тягам, добавить по подходу в подтягиваниях."},
            {"week": 4, "adjustment": "Разгрузка: -10% к весам, сохранить объём повторов."},
        ],
    },
    "sync_note": "Тренировочные дни калорийнее дней отдыха за счёт углеводов вокруг нагрузки.",
    "nutrition_analysis": {
        "fiber_g_target": 35,
        "sugar_g_limit": 50,
        "saturated_fat_g_limit": 22,
        "complex_vs_simple_carbs": {
            "assessment": "По снапшоту углеводы во многом из быстрых источников вечером.",
            "target": "Сдвинуть ≥70% углеводов в сложные (крупы, бобовые, овощи).",
        },
        "fiber": {
            "assessment": "Клетчатка ниже нормы при средних 200 г углеводов.",
            "target": "Довести до 30–35 г/сут за счёт овощей и цельных круп.",
        },
        "sugar": {
            "assessment": "Добавленный сахар умеренный, но скачет в дни отдыха.",
            "target": "Держать добавленный сахар < 50 г/сут.",
        },
        "saturated_fat": {
            "assessment": "Насыщенные жиры около верхней границы.",
            "target": "Не более ~10% калорий из насыщенных жиров.",
        },
        "protein_quality": {
            "assessment": "Белок 170 г распределён неравномерно по дню.",
            "target": "20–40 г белка в каждый из 3–4 приёмов пищи.",
        },
        "summary": "Калораж и белок в норме; работать над качеством углеводов и клетчаткой.",
    },
    "evidence_narrative": (
        "## Энергетический баланс\n"
        "Для набора массы умеренный профицit ~200–300 ккал поддерживает рост мышц без "
        "лишнего жира [10-1249-mss-0000000000001764]. Под цель важнее стабильность, чем "
        "скорость.\n\n"
        "## Белок: количество и распределение\n"
        "Достаточное потребление белка усиливает прирост силы и массы при силовом тренинге "
        "[10-1079-095442299108728956]; равномерное распределение по приёмам повышает "
        "суммарный синтез.\n\n"
        "## Тренировочный объём и добавки\n"
        "Недельный объём дозозависимо связан с гипертрофией "
        "[10-1249-mss-0000000000001764], а тайминг питания вокруг нагрузки поддерживает "
        "адаптации [10-1249-01-mss-0000233790-08788-3e].\n\n"
        "## Ближайшие шаги\n"
        "Добавить клетчатку, выровнять белок по приёмам, держать прогрессию малыми шагами."
    ),
    "citations": [
        {
            "id": "10-1249-mss-0000000000001764",
            "title": "Resistance Training Volume Enhances Muscle Hypertrophy",
            "authors": ["Schoenfeld BJ"],
            "year": 2018,
            "url_or_doi": "10.1249/MSS.0000000000001764",
            "claim": "Недельный объём силовых дозозависимо связан с гипертрофией.",
        },
        {
            "id": "10-1079-095442299108728956",
            "title": "Nutritional ergogenic aids and exercise performance",
            "authors": ["Williams MH"],
            "year": 1999,
            "url_or_doi": "10.1079/095442299108728956",
            "claim": "Достаточный белок и питание поддерживают работоспособность и адаптации.",
        },
        {
            "id": "10-1249-01-mss-0000233790-08788-3e",
            "title": "Effects of Supplement Timing and Resistance Exercise",
            "authors": ["Cribb PJ", "Hayes A"],
            "year": 2006,
            "url_or_doi": "10.1249/01.mss.0000233790.08788.3e",
            "claim": "Тайминг питания вокруг тренировки поддерживает рост массы и силы.",
        },
    ],
}


def plan_json_schema() -> dict[str, Any]:
    """JSON-схема (Draft) корневой модели — машиночитаемый контракт ответа."""
    return RecommendationPlan.model_json_schema()


def parse_plan(raw: str, valid_ids: frozenset[str] | None = None) -> RecommendationPlan:
    """Распарсить и провалидировать JSON-текст ответа модели в ``RecommendationPlan``.

    Бросает ``InvalidPlanError`` на невалидном JSON или нарушении схемы — это и есть
    «отбраковка». Текст НЕ предобрабатывается (никакой чистки markdown/```): контракт
    требует чистый JSON, а замазывание нарушений скрыло бы реальную проблему.

    ``valid_ids`` (если задан) — множество допустимых id цитат корпуса: каждая цитата
    обязана ссылаться на существующую работу, иначе отбраковка. None — проверку id
    пропускаем (юнит-тест схемы / ре-валидация старой записи), структуру всё равно проверяем.
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise InvalidPlanError(f"ответ модели — невалидный JSON: {exc}") from exc
    context = {"valid_citation_ids": valid_ids} if valid_ids is not None else None
    try:
        return RecommendationPlan.model_validate(data, context=context)
    except ValidationError as exc:
        raise InvalidPlanError(f"ответ модели не соответствует схеме: {exc}") from exc


def generate_valid_plan(
    produce: Callable[[], str], attempts: int = 3, valid_ids: frozenset[str] | None = None
) -> RecommendationPlan:
    """Получить валидный план: звать ``produce()`` и валидировать, ретраить отбраковку.

    ``produce`` — функция без аргументов, возвращающая сырой текст ответа модели (обёртка
    над вызовом LLM; намеренно абстрагирована, чтобы схему можно было тестировать и
    переиспользовать без сети). На ``InvalidPlanError`` повторяет вызов до ``attempts``
    раз; исчерпав попытки — пробрасывает последнюю ``InvalidPlanError``. ``valid_ids``
    пробрасывается в ``parse_plan`` (проверка существования цитат в корпусе).
    """
    if attempts < 1:
        raise ValueError("attempts должен быть >= 1")
    last_error: InvalidPlanError | None = None
    for _ in range(attempts):
        try:
            return parse_plan(produce(), valid_ids)
        except InvalidPlanError as exc:
            last_error = exc
    assert last_error is not None  # цикл выполнился ≥1 раз и не вернул результат
    raise last_error
