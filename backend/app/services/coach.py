"""Логика коуча (S5.8): по состоянию дня → категория → случайная фраза.

Состояние дня (``DayState``) — семантический сигнал, который коуч комментирует:
пропуск логирования, успешно закрытый день или достигнутая стрик-веха. Каждому
состоянию однозначно соответствует категория фраз из ``coach_phrases`` (S5.7),
откуда берётся случайная реплика.

``pick_phrase`` не повторяет одну и ту же фразу подряд: принимает ранее показанную
фразу и исключает её, пока в категории есть альтернатива («по возможности» из
критериев приёмки). Функция чистая — память о прошлой фразе держит вызывающий код,
состояние модуля не мутируется.
"""

import random
from enum import StrEnum

from app.services.coach_phrases import phrases_for


class DayState(StrEnum):
    """Состояние дня, которое комментирует коуч."""

    MISSED = "missed"  # пропуск логирования
    SUCCESS = "success"  # день закрыт по плану
    STREAK = "streak"  # достигнута стрик-веха


# Состояние дня → категория фраз (категории см. CATEGORIES в coach_phrases).
_STATE_TO_CATEGORY: dict[DayState, str] = {
    DayState.MISSED: "miss",
    DayState.SUCCESS: "success",
    DayState.STREAK: "streak",
}


def category_for(state: DayState) -> str:
    """Категория фраз для состояния дня. ``KeyError`` при неучтённом состоянии."""
    return _STATE_TO_CATEGORY[state]


def pick_phrase(
    state: DayState,
    *,
    previous: str | None = None,
    rng: random.Random | None = None,
) -> str:
    """Случайная фраза для состояния дня, по возможности не равная ``previous``.

    ``previous`` — последняя показанная фраза: исключаем её, чтобы не повторять
    реплику подряд. Если в категории только она — выбора нет, возвращаем её же.
    ``rng`` инжектируется в тестах ради детерминизма.
    """
    phrases = phrases_for(category_for(state))
    candidates = tuple(p for p in phrases if p != previous) or phrases
    # ponytail: stdlib random — подбор фразы не security-чувствителен
    return (rng or random).choice(candidates)
