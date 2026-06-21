"""SQLModel-модели. Импорт здесь регистрирует таблицы в SQLModel.metadata."""

from app.models.achievement import Achievement, AchievementProof
from app.models.activity import ActivityDay, HrZones
from app.models.body import BodyMeasurement, InbodyMeasurement
from app.models.deficit import DeficitDay
from app.models.goal import SmartGoal
from app.models.nutrition import FoodEntry
from app.models.recommendation import Recommendation
from app.models.sport import Exercise, Sport
from app.models.user import User
from app.models.workout import (
    CardioLog,
    PersonalRecord,
    SkillLog,
    StrengthSet,
    WorkoutSession,
)

__all__ = [
    "Achievement",
    "AchievementProof",
    "ActivityDay",
    "BodyMeasurement",
    "CardioLog",
    "DeficitDay",
    "Exercise",
    "FoodEntry",
    "HrZones",
    "InbodyMeasurement",
    "PersonalRecord",
    "Recommendation",
    "SkillLog",
    "Sport",
    "SmartGoal",
    "StrengthSet",
    "User",
    "WorkoutSession",
]
