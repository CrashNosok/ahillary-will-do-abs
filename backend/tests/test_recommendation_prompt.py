"""Системный промпт рекомендаций (S4.2): покрытие требований карточки.

Сети нет — проверяем сам текст промпта и контракт его выхода: каждое требование
безопасности из карточки присутствует, выход требуется строго JSON, а встроенный
пример валиден по объявленной схеме (перечни значений — единый источник правды).
"""

import json

from app.services.recommendation_prompt import (
    AREAS,
    FLAG_KINDS,
    PRIORITIES,
    RESPONSE_EXAMPLE,
    SYSTEM_PROMPT,
)


def test_prompt_requires_strict_json_output():
    """Критерий приёмки: промпт требует структурированный JSON-выход."""
    low = SYSTEM_PROMPT.lower()
    assert "json" in low
    assert "ровно один json" in low  # строго один объект, без обвеса
    assert "markdown" in low  # явный запрет markdown/```


def test_prompt_covers_safety_requirements():
    """Все пункты «Сделать» из карточки явно прописаны в промпте."""
    low = SYSTEM_PROMPT.lower()
    assert "устойчив" in low  # устойчивый безопасный подход
    assert "дефицит" in low and "агрессивн" in low  # помечать слишком агрессивный дефицит
    assert "прогрессивн" in low and "постепенно" in low  # нагрузку поднимать прогрессивно
    assert "углевод" in low  # связка еда↔тренировка (пример про углеводы в день силовой)
    assert "тон" in low and "токсичн" in low  # тон без токсичности


def test_prompt_lists_enum_values():
    """Перечни допустимых значений подставлены в текст промпта (схема не разъехалась)."""
    for value in (*AREAS, *FLAG_KINDS, *PRIORITIES):
        assert value in SYSTEM_PROMPT


def test_prompt_embeds_valid_json_example():
    """Встроенный в промпт пример ответа парсится как JSON (контракт корректен)."""
    marker = "Пример валидного ответа:\n"
    example_text = SYSTEM_PROMPT.split(marker, 1)[1]
    assert json.loads(example_text) == RESPONSE_EXAMPLE


def test_response_example_matches_schema():
    """Эталонный пример соответствует объявленной схеме выхода."""
    assert set(RESPONSE_EXAMPLE) == {
        "summary",
        "assessment",
        "recommendations",
        "safety_flags",
        "food_training_sync",
    }
    assert set(RESPONSE_EXAMPLE["assessment"]) == {"deficit", "training_load", "goal_progress"}

    for rec in RESPONSE_EXAMPLE["recommendations"]:
        assert set(rec) == {"area", "action", "why", "priority"}
        assert rec["area"] in AREAS
        assert rec["priority"] in PRIORITIES

    for flag in RESPONSE_EXAMPLE["safety_flags"]:
        assert set(flag) == {"kind", "message"}
        assert flag["kind"] in FLAG_KINDS
