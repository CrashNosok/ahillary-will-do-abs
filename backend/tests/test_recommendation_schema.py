"""Структурированная схема рекомендаций (S4.3): покрытие критериев приёмки.

Сети нет — проверяем саму схему и логику отбраковки/ретрая на синтетических ответах.
Два критерия карточки:
1. схема валидируется (валидный план принимается, нарушения — отбраковываются);
2. невалидный ответ модели отбраковывается/ретраится.
"""

import copy
import json

import pytest

from app.services.recommendation_schema import (
    PLAN_EXAMPLE,
    InvalidPlanError,
    RecommendationPlan,
    generate_valid_plan,
    parse_plan,
    plan_json_schema,
)


def _example_json(mutate=None) -> str:
    """JSON-текст валидного примера; mutate(dict) может его испортить перед сериализацией."""
    data = copy.deepcopy(PLAN_EXAMPLE)
    if mutate is not None:
        mutate(data)
    return json.dumps(data, ensure_ascii=False)


# --- Критерий 1: схема валидируется -------------------------------------------------


def test_plan_example_is_valid():
    """Эталонный пример проходит валидацию и даёт корневую модель."""
    plan = parse_plan(_example_json())
    assert isinstance(plan, RecommendationPlan)
    assert plan.workout_plan.days_per_week == 3
    assert plan.meal_plan.training_day.day_type.value == "training"


def test_json_schema_exposes_all_required():
    """JSON-схема содержит планы + доказательную часть как обязательные поля."""
    schema = plan_json_schema()
    required = {
        "meal_plan",
        "workout_plan",
        "sync_note",
        "nutrition_analysis",
        "evidence_narrative",
        "citations",
    }
    assert required <= set(schema["properties"])
    assert set(schema["required"]) == required


def test_bodyweight_exercise_allows_null_weight():
    """Рабочий вес необязателен: упражнение с собственным весом (null) валидно."""
    plan = parse_plan(_example_json())
    plank = plan.workout_plan.schedule[0].exercises[-1]
    assert plank.working_weight_kg is None


# --- Критерий 1: нарушения схемы отбраковываются ------------------------------------


def test_extra_field_rejected():
    """Лишний ключ в ответе модели = отбраковка (схема строгая, extra='forbid')."""
    with pytest.raises(InvalidPlanError):
        parse_plan(_example_json(lambda d: d.update(unexpected="x")))


def test_non_positive_calories_rejected():
    """Калорийность дня должна быть > 0."""
    with pytest.raises(InvalidPlanError):
        parse_plan(_example_json(lambda d: d["meal_plan"]["rest_day"].update(calories=0)))


def test_negative_macros_rejected():
    """Отрицательные макросы недопустимы."""
    with pytest.raises(InvalidPlanError):

        def mutate(d):
            d["meal_plan"]["training_day"]["macros"]["protein_g"] = -5

        parse_plan(_example_json(mutate))


def test_bad_enum_day_type_rejected():
    """day_type вне перечня training/rest — отбраковка."""
    with pytest.raises(InvalidPlanError):
        parse_plan(_example_json(lambda d: d["meal_plan"]["rest_day"].update(day_type="cheat")))


def test_schedule_length_must_match_days_per_week():
    """Длина расписания обязана совпадать с days_per_week (связность плана тренировок)."""
    with pytest.raises(InvalidPlanError):
        parse_plan(_example_json(lambda d: d["workout_plan"].update(days_per_week=5)))


def test_schedule_days_must_be_sequential():
    """Дни расписания нумеруются 1..N без пропусков."""

    def mutate(d):
        d["workout_plan"]["schedule"][2]["day"] = 9

    with pytest.raises(InvalidPlanError):
        parse_plan(_example_json(mutate))


def test_progression_weeks_must_be_sequential():
    """Недели прогрессии нумеруются 1..N без пропусков."""

    def mutate(d):
        d["workout_plan"]["weekly_progression"][1]["week"] = 7

    with pytest.raises(InvalidPlanError):
        parse_plan(_example_json(mutate))


def test_training_day_calories_not_below_rest():
    """Увязка двух планов: тренировочный день не может быть калорийно беднее дня отдыха."""

    def mutate(d):
        d["meal_plan"]["training_day"]["calories"] = 1500  # < rest_day (2100)

    with pytest.raises(InvalidPlanError):
        parse_plan(_example_json(mutate))


def test_empty_meals_rejected():
    """В дне должен быть хотя бы один приём пищи."""
    with pytest.raises(InvalidPlanError):
        parse_plan(_example_json(lambda d: d["meal_plan"]["rest_day"].update(meals=[])))


def test_broken_json_rejected():
    """Битый JSON отбраковывается как InvalidPlanError, а не падает наружу."""
    with pytest.raises(InvalidPlanError):
        parse_plan("{не json, это текст модели```")


# --- Доказательная часть: нутриент-разбор + нарратив + цитаты ------------------------


def test_nutrition_analysis_required():
    """Детальный нутриент-разбор обязателен."""
    with pytest.raises(InvalidPlanError):
        parse_plan(_example_json(lambda d: d.pop("nutrition_analysis")))


def test_evidence_narrative_min_length():
    """Слишком короткий нарратив отбраковывается (отчёт должен быть содержательным)."""
    with pytest.raises(InvalidPlanError):
        parse_plan(_example_json(lambda d: d.update(evidence_narrative="коротко")))


def test_citations_min_count():
    """Минимум 3 цитаты — иначе отчёт не обоснован."""
    with pytest.raises(InvalidPlanError):
        parse_plan(_example_json(lambda d: d.update(citations=d["citations"][:2])))


def test_citation_extra_field_rejected():
    """Лишний ключ внутри цитаты — отбраковка (строгая схема)."""

    def mutate(d):
        d["citations"][0]["foo"] = "bar"

    with pytest.raises(InvalidPlanError):
        parse_plan(_example_json(mutate))


def test_citation_unknown_id_rejected_with_context():
    """С valid_ids цитата на отсутствующую в корпусе работу отбраковывается."""
    with pytest.raises(InvalidPlanError):
        parse_plan(_example_json(), valid_ids=frozenset({"a", "b", "c"}))


def test_citation_ids_accepted_when_in_corpus():
    """Если id цитат входят в valid_ids — план валиден."""
    ids = frozenset(c["id"] for c in PLAN_EXAMPLE["citations"])
    plan = parse_plan(_example_json(), valid_ids=ids)
    assert isinstance(plan, RecommendationPlan)


def test_citation_check_skipped_without_context():
    """Без valid_ids проверка существования id не запускается (старые записи/юнит-тест)."""
    plan = parse_plan(_example_json())
    assert len(plan.citations) >= 3


# --- Критерий 2: невалидный ответ отбраковывается/ретраится -------------------------


def test_generate_returns_first_valid_without_extra_calls():
    """Если первый ответ валиден — ретраев нет (ровно один вызов генератора)."""
    calls = {"n": 0}

    def produce():
        calls["n"] += 1
        return _example_json()

    plan = generate_valid_plan(produce, attempts=3)
    assert isinstance(plan, RecommendationPlan)
    assert calls["n"] == 1


def test_generate_retries_until_valid():
    """Невалидные ответы ретраятся; первый валидный — возвращается."""
    replies = iter(["сломанный ответ", _example_json(lambda d: d.update(x=1)), _example_json()])
    calls = {"n": 0}

    def produce():
        calls["n"] += 1
        return next(replies)

    plan = generate_valid_plan(produce, attempts=3)
    assert isinstance(plan, RecommendationPlan)
    assert calls["n"] == 3  # два невалидных + один валидный


def test_generate_exhausts_attempts_and_raises():
    """Если все попытки невалидны — ровно attempts вызовов и InvalidPlanError."""
    calls = {"n": 0}

    def produce():
        calls["n"] += 1
        return "always broken"

    with pytest.raises(InvalidPlanError):
        generate_valid_plan(produce, attempts=2)
    assert calls["n"] == 2


def test_generate_requires_positive_attempts():
    """attempts < 1 — ошибка использования, не молчаливый no-op."""
    with pytest.raises(ValueError):
        generate_valid_plan(lambda: _example_json(), attempts=0)
