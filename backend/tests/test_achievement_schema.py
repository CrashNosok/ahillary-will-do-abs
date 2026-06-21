"""Схема генератора ачивок (S5.1): покрытие критериев приёмки.

Сети нет — проверяем саму схему и логику отбраковки/ретрая на синтетических ответах.
Два критерия карточки:
1. ачивки тируются по сложности (>= 2 разных тира; иначе отбраковка);
2. новичку не предлагаются опасные элементы (is_dangerous / тир выше потолка → отбраковка).
"""

import copy
import json

import pytest

from app.services.achievement_schema import (
    ACHIEVEMENT_SET_EXAMPLE,
    AchievementSet,
    AthleteLevel,
    InvalidAchievementSetError,
    achievement_set_json_schema,
    generate_valid_achievement_set,
    parse_achievement_set,
)


def _example_json(mutate=None) -> str:
    """JSON-текст валидного примера; mutate(dict) может его испортить перед сериализацией."""
    data = copy.deepcopy(ACHIEVEMENT_SET_EXAMPLE)
    if mutate is not None:
        mutate(data)
    return json.dumps(data, ensure_ascii=False)


# --- Критерий 1: тирование по сложности ---------------------------------------------


def test_example_is_valid_and_tiered():
    """Эталонный пример проходит валидацию и охватывает >= 2 тира сложности."""
    result = parse_achievement_set(_example_json(), expected_level=AthleteLevel.beginner)
    assert isinstance(result, AchievementSet)
    assert len({a.tier for a in result.achievements}) >= 2  # тируется по сложности


def test_single_tier_set_is_rejected():
    """Все ачивки одного тира → отбраковка (нет тирования по сложности)."""

    def to_one_tier(data):
        for a in data["achievements"]:
            a["tier"] = "foundation"

    with pytest.raises(InvalidAchievementSetError):
        parse_achievement_set(_example_json(to_one_tier), expected_level=AthleteLevel.beginner)


def test_json_schema_exposes_core_fields():
    """JSON-схема существует и объявляет ключевые поля контракта обязательными."""
    schema = achievement_set_json_schema()
    assert {"sport", "level", "achievements"} <= set(schema["properties"])
    assert set(schema["required"]) >= {"sport", "level", "achievements"}


# --- Критерий 2: безопасность под уровень (новичку — без опасного) -------------------


def test_beginner_rejects_dangerous_element():
    """Новичку нельзя is_dangerous=true — такой набор отбраковывается."""

    def make_dangerous(data):
        data["achievements"][-1]["is_dangerous"] = True

    with pytest.raises(InvalidAchievementSetError):
        parse_achievement_set(_example_json(make_dangerous), expected_level=AthleteLevel.beginner)


def test_beginner_rejects_tier_above_ceiling():
    """Новичку нельзя тир выше intermediate (advanced/elite — риск травмы) → отбраковка."""

    def raise_tier(data):
        data["achievements"][-1]["tier"] = "advanced"

    with pytest.raises(InvalidAchievementSetError):
        parse_achievement_set(_example_json(raise_tier), expected_level=AthleteLevel.beginner)


def test_advanced_allows_elite_and_dangerous():
    """Продвинутому можно elite-тир и опасные трюки — это и есть смысл уровня."""
    data = copy.deepcopy(ACHIEVEMENT_SET_EXAMPLE)
    data["level"] = "advanced"
    data["achievements"][-1]["tier"] = "elite"
    data["achievements"][-1]["is_dangerous"] = True
    result = parse_achievement_set(
        json.dumps(data, ensure_ascii=False), expected_level=AthleteLevel.advanced
    )
    assert any(a.is_dangerous for a in result.achievements)


def test_level_mismatch_is_rejected():
    """Уровень ответа должен совпадать с запрошенным — иначе обход защиты новичка."""
    # Пример объявляет beginner; просим intermediate → несовпадение = отбраковка.
    with pytest.raises(InvalidAchievementSetError):
        parse_achievement_set(_example_json(), expected_level=AthleteLevel.intermediate)


# --- Отбраковка/ретрай --------------------------------------------------------------


def test_broken_json_is_rejected():
    """Битый JSON → InvalidAchievementSetError, без падения парсера."""
    with pytest.raises(InvalidAchievementSetError):
        parse_achievement_set("{ это не json", expected_level=AthleteLevel.beginner)


def test_extra_key_is_rejected():
    """Лишний ключ в ответе (extra='forbid') → отбраковка."""

    def add_extra(data):
        data["unexpected"] = 1

    with pytest.raises(InvalidAchievementSetError):
        parse_achievement_set(_example_json(add_extra), expected_level=AthleteLevel.beginner)


def test_generate_retries_invalid_then_valid():
    """Первый ответ битый, второй валиден: ретрай возвращает валидный набор."""
    queue = ["{ битый", _example_json()]  # pop(0) — FIFO: сначала битый, потом валидный

    result = generate_valid_achievement_set(
        lambda: queue.pop(0), expected_level=AthleteLevel.beginner, attempts=3
    )
    assert isinstance(result, AchievementSet)


def test_generate_all_invalid_raises():
    """Все попытки отбракованы → пробрасывается InvalidAchievementSetError."""
    queue = ["{ битый", "тоже не json", "[]"]

    with pytest.raises(InvalidAchievementSetError):
        generate_valid_achievement_set(
            lambda: queue.pop(0), expected_level=AthleteLevel.beginner, attempts=3
        )
