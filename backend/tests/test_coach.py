"""Логика коуча (S5.8): состояние дня → категория → фраза без повтора подряд."""

import random

import pytest

from app.services.coach import DayState, category_for, pick_phrase
from app.services.coach_phrases import phrases_for


def test_category_for_maps_each_state():
    assert category_for(DayState.MISSED) == "miss"
    assert category_for(DayState.SUCCESS) == "success"
    assert category_for(DayState.STREAK) == "streak"


@pytest.mark.parametrize("state", list(DayState))
def test_pick_phrase_comes_from_state_category(state):
    phrase = pick_phrase(state, rng=random.Random(0))
    assert phrase in phrases_for(category_for(state))


@pytest.mark.parametrize("state", list(DayState))
def test_pick_phrase_excludes_previous_when_alternative_exists(state):
    pool = phrases_for(category_for(state))
    assert len(pool) > 1, "в наборе должно быть из чего выбрать"
    rng = random.Random(123)
    previous = pool[0]
    for _ in range(50):
        nxt = pick_phrase(state, previous=previous, rng=rng)
        assert nxt != previous
        previous = nxt


@pytest.mark.parametrize("state", list(DayState))
def test_pick_phrase_uses_whole_category(state):
    """Подбор случайный: за много прогонов перебирает все фразы категории."""
    rng = random.Random(2024)
    pool = set(phrases_for(category_for(state)))
    got = {pick_phrase(state, rng=rng) for _ in range(200)}
    assert got == pool


def test_single_phrase_category_falls_back_to_repeat(monkeypatch):
    """«По возможности»: если в категории одна фраза — возвращаем её же."""
    only = ("Единственная фраза.",)
    monkeypatch.setattr("app.services.coach.phrases_for", lambda _category: only)
    assert pick_phrase(DayState.MISSED, previous="Единственная фраза.") == "Единственная фраза."
