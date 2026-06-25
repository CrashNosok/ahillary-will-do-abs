"""Каталог тренировок (S1.2/S3.1): вид спорта и упражнение.

sport — дисциплина (калистеника, бег, силовая…); на неё ссылаются сессии и ачивки.
category делит дисциплины по таксономии M1 (валидируется на CRUD, S3.1).
exercise — конкретное упражнение внутри вида спорта (FK sport_id); на него ссылаются
подходы/логи/рекорды. kind отделяет силовое/кардио/навык, unit — дефолтная единица.
"""

from enum import StrEnum

from sqlmodel import Field, SQLModel


class SportCategory(StrEnum):
    """Таксономия дисциплин M1 — категория вида спорта (Sport.category, M1·B14).

    Сменила старую тройку strength/cardio/skill: cardio→endurance, skill→action
    (миграция M1·B14). value == name, колонка sport.category — plain VARCHAR.
    """

    strength = "strength"
    endurance = "endurance"
    combat = "combat"
    team = "team"
    racket = "racket"
    action = "action"
    precision = "precision"
    artistic = "artistic"
    other = "other"


class Sport(SQLModel, table=True):
    __tablename__ = "sport"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    category: SportCategory
    description: str | None = None  # короткая подпись (S3.1)
    # M5·B22 «rich-поля» каталога:
    slug: str | None = Field(default=None, unique=True, index=True)  # ЧПУ, авто из name
    long_description: str | None = None  # развёрнутое описание дисциплины
    is_global: bool = Field(default=False)  # встроенная дисциплина vs заведённая юзером


class Exercise(SQLModel, table=True):
    __tablename__ = "exercise"

    id: int | None = Field(default=None, primary_key=True)
    sport_id: int = Field(foreign_key="sport.id", index=True)
    name: str
    kind: str | None = None  # strength | cardio | skill — как логировать упражнение
    unit: str | None = None  # дефолтная единица: кг / повторы / сек / км
    notes: str | None = None  # произвольная заметка (техника, хват, оговорки) — S3.2
