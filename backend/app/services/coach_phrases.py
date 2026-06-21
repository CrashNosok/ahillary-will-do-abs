"""Фразы коуча (S5.7): выносимый редактируемый набор, грузится в рантайме.

Тексты живут в ``coach_phrases.json`` рядом с этим модулем — редактируешь JSON,
кода не трогаешь. Категории: ``miss`` (промах/пропуск), ``success`` (выполнено),
``streak`` (серия подряд). Тон — дерзкий, но без токсичности и стыда за тело.

Загрузка ленивая и кэшируется на процесс (``lru_cache``): файл читается один раз
при первом обращении в рантайме. Контракт категорий валидируется на границе —
внешний редактируемый файл не доверенный источник, поэтому любое нарушение даёт
понятный ``CoachPhrasesError``, а не падение где-то ниже по стеку.
"""

import json
from functools import lru_cache
from pathlib import Path

# Категории фраз — единый источник правды для загрузчика и тестов.
CATEGORIES = ("miss", "success", "streak")

_PHRASES_FILE = Path(__file__).with_name("coach_phrases.json")


class CoachPhrasesError(RuntimeError):
    """Файл фраз отсутствует, не парсится или нарушает контракт категорий."""


@lru_cache(maxsize=1)
def load_phrases() -> dict[str, tuple[str, ...]]:
    """Прочитать и провалидировать ``coach_phrases.json`` (один раз за процесс).

    Возвращает ``{категория: кортеж непустых фраз}`` ровно по ``CATEGORIES``.
    Любое нарушение контракта — ``CoachPhrasesError`` с понятным сообщением.
    """
    try:
        raw = json.loads(_PHRASES_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CoachPhrasesError(f"Файл фраз не найден: {_PHRASES_FILE}") from exc
    except json.JSONDecodeError as exc:
        raise CoachPhrasesError(f"coach_phrases.json не парсится: {exc}") from exc

    if not isinstance(raw, dict):
        raise CoachPhrasesError("coach_phrases.json: ожидался объект {категория: [фразы]}.")

    result: dict[str, tuple[str, ...]] = {}
    for category in CATEGORIES:
        items = raw.get(category)
        if not isinstance(items, list) or not items:
            raise CoachPhrasesError(f"Категория '{category}': нужен непустой список фраз.")
        if not all(isinstance(phrase, str) and phrase.strip() for phrase in items):
            raise CoachPhrasesError(f"Категория '{category}': все фразы — непустые строки.")
        result[category] = tuple(items)
    return result


def phrases_for(category: str) -> tuple[str, ...]:
    """Фразы одной категории (одна из ``CATEGORIES``). ``KeyError`` при неизвестной."""
    phrases = load_phrases()
    if category not in phrases:
        raise KeyError(f"Неизвестная категория фраз: {category!r}. Доступно: {CATEGORIES}.")
    return phrases[category]
