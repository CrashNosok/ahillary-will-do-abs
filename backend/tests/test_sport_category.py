"""M1·B13: enum SportCategory — таксономия дисциплин M1 + legacy-алиас SportType.

Карточка вводит SportCategory с фиксированным набором категорий как основу M1.
SportType (старая тройка) пока остаётся активным — на него опираются каталог
sport, API /sports, фронт и данные; перевод на SportCategory — отдельные карточки.
"""

from app.models import SportCategory, SportType

# Точный набор из карточки M1·B13 (значение == имя у StrEnum).
_EXPECTED_CATEGORIES = (
    "strength",
    "endurance",
    "combat",
    "team",
    "racket",
    "action",
    "precision",
    "artistic",
    "other",
)


def test_sport_category_has_exact_card_values():
    # критерий M1·B13: SportCategory = ровно 9 категорий из карточки, value == name
    assert tuple(c.value for c in SportCategory) == _EXPECTED_CATEGORIES
    assert all(c.value == c.name for c in SportCategory)


def test_sport_category_values_are_plain_strings():
    # StrEnum: значение можно использовать как обычную строку (валидация/сериализация)
    assert SportCategory.endurance == "endurance"
    assert f"{SportCategory.combat}" == "combat"


def test_sport_type_legacy_alias_still_active():
    # критерий M1·B13: старый SportType сохранён (strength/cardio/skill) — ничего не сломано
    assert tuple(t.value for t in SportType) == ("strength", "cardio", "skill")
