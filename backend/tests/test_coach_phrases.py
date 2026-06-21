"""Фразы коуча (S5.7): рантайм-загрузка, контракт категорий, грубый гейт тона."""

import json

import pytest

from app.services import coach_phrases
from app.services.coach_phrases import (
    CATEGORIES,
    CoachPhrasesError,
    load_phrases,
    phrases_for,
)


def test_loads_at_runtime_with_all_categories():
    phrases = load_phrases()
    assert set(phrases) == set(CATEGORIES)
    for category in CATEGORIES:
        assert phrases[category], f"категория {category} пуста"
        assert all(isinstance(p, str) and p.strip() for p in phrases[category])


def test_phrases_for_returns_each_category():
    for category in CATEGORIES:
        assert phrases_for(category) == load_phrases()[category]


def test_phrases_for_unknown_category_raises():
    with pytest.raises(KeyError):
        phrases_for("nonsense")


def test_invalid_file_raises_clear_error(tmp_path, monkeypatch):
    bad = tmp_path / "coach_phrases.json"
    bad.write_text(json.dumps({"miss": []}), encoding="utf-8")
    monkeypatch.setattr(coach_phrases, "_PHRASES_FILE", bad)
    load_phrases.cache_clear()
    with pytest.raises(CoachPhrasesError):
        load_phrases()
    load_phrases.cache_clear()  # не оставляем кэш битого файла другим тестам


# Тон: дерзкий, но без токсичности и стыда за тело (acceptance S5.7). Денилист —
# только очевидно-оскорбительное / боди-шейм: грубый авто-гейт под ручное ревью.
_BANNED = (
    "жирн",
    "толст",
    "пузо",
    "тюфяк",
    "урод",
    "тупой",
    "тупиц",
    "идиот",
    "ничтожеств",
    "позорищ",
    "слабак",
)


def test_tone_has_no_toxic_or_bodyshame_words():
    blob = " ".join(p.lower() for ps in load_phrases().values() for p in ps)
    hits = [word for word in _BANNED if word in blob]
    assert not hits, f"запрещённые по тону слова: {hits}"
