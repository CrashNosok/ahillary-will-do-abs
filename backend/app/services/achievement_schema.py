"""Схема генератора ачивок (S5.1): тиры сложности + безопасность под уровень атлета.

Карточка просит набор ачивок под дисциплину, ТИРОВАННЫЙ по сложности, и уважающий уровень
пользователя: новичку — без опасных трюков. Обе гарантии зашиты в саму схему, а не держатся
на честном слове модели:

- каждая ачивка несёт ``tier`` (foundation < intermediate < advanced < elite) и честный
  флаг ``is_dangerous`` (трюк с реальным риском травмы / обязательной страховкой);
- ``AchievementSet`` валидирует, что набор охватывает >= 2 разных тира (это и есть «тируется
  по сложности»);
- для ``level == beginner`` ни одна ачивка не может быть ``is_dangerous`` и не может быть выше
  потолка тира для уровня — нарушение ОТБРАКОВЫВАЕТСЯ.

Схема строгая (``extra="forbid"``): лишний ключ в ответе модели = отбраковка. Отбраковка
ретраится (``generate_valid_achievement_set``) — как и в S4.3.

Публичное API:
- ``AchievementSet`` — корневая Pydantic-модель ответа;
- ``ACHIEVEMENT_SET_EXAMPLE`` — валидный эталонный пример (образец для промпта и фикстура);
- ``achievement_set_json_schema()`` — JSON-схема корневой модели;
- ``parse_achievement_set(raw, expected_level)`` — распарсить+провалидировать ответ модели
  (``InvalidAchievementSetError`` на битом JSON, нарушении схемы или несовпадении уровня);
- ``generate_valid_achievement_set(produce, expected_level, attempts)`` — звать генератор и
  валидировать; отбраковку ретраить до ``attempts`` раз.
"""

import json
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class _Strict(BaseModel):
    """Базовая модель схемы: лишние ключи запрещены (строгая отбраковка ответа модели)."""

    model_config = ConfigDict(extra="forbid")


class AthleteLevel(StrEnum):
    """Уровень пользователя — вход генератора. beginner получает только безопасные ачивки."""

    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"


class Tier(StrEnum):
    """Тир сложности ачивки по возрастанию. elite — экстремальные/опасные элементы."""

    foundation = "foundation"
    intermediate = "intermediate"
    advanced = "advanced"
    elite = "elite"


# Порядок тиров по возрастанию сложности — единый источник для валидации и тестов.
TIER_ORDER: tuple[Tier, ...] = (Tier.foundation, Tier.intermediate, Tier.advanced, Tier.elite)
_TIER_RANK: dict[Tier, int] = {tier: i for i, tier in enumerate(TIER_ORDER)}

# Потолок тира по уровню атлета: новичку не предлагаем advanced/elite (риск травмы).
_MAX_TIER_FOR_LEVEL: dict[AthleteLevel, Tier] = {
    AthleteLevel.beginner: Tier.intermediate,
    AthleteLevel.intermediate: Tier.advanced,
    AthleteLevel.advanced: Tier.elite,
}

# Сколько минимум ачивок в наборе — иначе тировать по сложности нечем.
_MIN_ACHIEVEMENTS = 3


class AchievementSpec(_Strict):
    """Одна ачивка: что освоить, тир сложности и честный флаг опасности элемента."""

    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    tier: Tier
    is_dangerous: bool  # трюк с реальным риском травмы / обязательной страховкой


class AchievementSet(_Strict):
    """Набор ачивок по дисциплине: тированный по сложности и безопасный под уровень."""

    sport: str = Field(min_length=1)
    level: AthleteLevel
    achievements: list[AchievementSpec] = Field(min_length=_MIN_ACHIEVEMENTS)

    @model_validator(mode="after")
    def _tiered_and_safe(self) -> "AchievementSet":
        # Критерий 1: тируется по сложности — набор охватывает >= 2 разных тира.
        if len({a.tier for a in self.achievements}) < 2:
            raise ValueError("ачивки должны быть тированы по сложности: нужно >= 2 разных тира")
        # Критерий 2: безопасность под уровень. Потолок тира + запрет опасного для новичка.
        ceiling = _MAX_TIER_FOR_LEVEL[self.level]
        ceiling_rank = _TIER_RANK[ceiling]
        for a in self.achievements:
            if self.level is AthleteLevel.beginner and a.is_dangerous:
                raise ValueError(
                    f"новичку нельзя опасные элементы: '{a.title}' помечен is_dangerous"
                )
            if _TIER_RANK[a.tier] > ceiling_rank:
                raise ValueError(
                    f"тир '{a.tier.value}' выше потолка '{ceiling.value}' "
                    f"для уровня '{self.level.value}'"
                )
        return self


class InvalidAchievementSetError(ValueError):
    """Ответ модели отбракован: битый JSON, нарушение схемы или несовпадение уровня."""


# Валидный эталонный пример (level=beginner): образец формы для промпта и фикстура тестов.
# Демонстрирует тирование (foundation→intermediate) и безопасность (нет is_dangerous,
# потолок тира не превышен) — продвинутые/опасные трюки вроде «рейли» новичку не попадают.
ACHIEVEMENT_SET_EXAMPLE: dict[str, Any] = {
    "sport": "Вейкборд",
    "level": "beginner",
    "achievements": [
        {
            "title": "Уверенный старт из воды",
            "description": "Встать на доску и проехать 50 метров за катером без падения.",
            "tier": "foundation",
            "is_dangerous": False,
        },
        {
            "title": "Контроль на ровной воде",
            "description": "Удерживать стойку и направление на дистанции 2 минуты подряд.",
            "tier": "foundation",
            "is_dangerous": False,
        },
        {
            "title": "Переход через кильватер",
            "description": "Плавно пересечь след катера в обе стороны без потери равновесия.",
            "tier": "intermediate",
            "is_dangerous": False,
        },
        {
            "title": "Олли на ровной воде",
            "description": "Контролируемый отрыв доски от воды без трамплина и приземление.",
            "tier": "intermediate",
            "is_dangerous": False,
        },
    ],
}


def achievement_set_json_schema() -> dict[str, Any]:
    """JSON-схема (Draft) корневой модели — машиночитаемый контракт ответа."""
    return AchievementSet.model_json_schema()


def parse_achievement_set(raw: str, *, expected_level: AthleteLevel) -> AchievementSet:
    """Распарсить и провалидировать JSON-текст ответа модели в ``AchievementSet``.

    Бросает ``InvalidAchievementSetError`` на невалидном JSON, нарушении схемы или если
    ``level`` в ответе не совпадает с запрошенным — это и есть «отбраковка». Проверка уровня
    обязательна: иначе модель могла бы обойти защиту новичка, объявив более высокий уровень.
    Текст НЕ предобрабатывается (никакой чистки markdown/```): контракт требует чистый JSON.
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise InvalidAchievementSetError(f"ответ модели — невалидный JSON: {exc}") from exc
    try:
        result = AchievementSet.model_validate(data)
    except ValidationError as exc:
        raise InvalidAchievementSetError(f"ответ модели не соответствует схеме: {exc}") from exc
    if result.level is not expected_level:
        raise InvalidAchievementSetError(
            f"уровень ответа '{result.level.value}' не совпадает с запрошенным "
            f"'{expected_level.value}'"
        )
    return result


def generate_valid_achievement_set(
    produce: Callable[[], str], *, expected_level: AthleteLevel, attempts: int = 3
) -> AchievementSet:
    """Получить валидный набор: звать ``produce()`` и валидировать, ретраить отбраковку.

    ``produce`` — функция без аргументов, возвращающая сырой текст ответа модели (обёртка
    над вызовом LLM; абстрагирована, чтобы схему можно было тестировать без сети). На
    ``InvalidAchievementSetError`` повторяет вызов до ``attempts`` раз; исчерпав попытки —
    пробрасывает последнюю ошибку.
    """
    if attempts < 1:
        raise ValueError("attempts должен быть >= 1")
    last_error: InvalidAchievementSetError | None = None
    for _ in range(attempts):
        try:
            return parse_achievement_set(produce(), expected_level=expected_level)
        except InvalidAchievementSetError as exc:
            last_error = exc
    assert last_error is not None  # цикл выполнился ≥1 раз и не вернул результат
    raise last_error
