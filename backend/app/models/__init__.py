"""SQLModel-модели. Импорт здесь регистрирует таблицы в SQLModel.metadata."""

from app.models.activity import ActivityDay, HrZones
from app.models.body import BodyMeasurement, InbodyMeasurement
from app.models.deficit import DeficitDay
from app.models.goal import SmartGoal
from app.models.nutrition import FoodEntry
from app.models.user import User

__all__ = [
    "ActivityDay",
    "BodyMeasurement",
    "DeficitDay",
    "FoodEntry",
    "HrZones",
    "InbodyMeasurement",
    "SmartGoal",
    "User",
]
