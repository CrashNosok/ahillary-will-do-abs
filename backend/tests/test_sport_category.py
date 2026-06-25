"""M1·B14: каталог sport переведён на таксономию SportCategory.

B13 ввёл SportCategory как основу при живом legacy-алиасе SportType; B14 — cutover:
Sport.category типизирован SportCategory, старый SportType удалён, значения
ремапнуты (cardio→endurance, skill→action) миграцией f9a2c7b51d84.
"""

from app.models import SportCategory
from app.models.sport import Sport

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


def test_retired_values_are_not_in_taxonomy():
    # критерий M1·B14: старая тройка снята — cardio/skill больше не валидны
    values = {c.value for c in SportCategory}
    assert "cardio" not in values and "skill" not in values


def test_sport_model_uses_category_field():
    # критерий M1·B14: поле модели переименовано type→category и типизировано SportCategory
    assert "category" in Sport.model_fields
    assert "type" not in Sport.model_fields
    sport = Sport(name="Бег", category=SportCategory.endurance)
    assert sport.category is SportCategory.endurance


def test_sport_type_legacy_alias_removed():
    # критерий M1·B14: временный legacy-алиас SportType удалён на cutover
    import app.models.sport as sport_module

    assert not hasattr(sport_module, "SportType")
