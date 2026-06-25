"""Каталог тренировок (S1.2/S3.1): вид спорта и упражнение.

sport — дисциплина (калистеника, бег, силовая…); на неё ссылаются сессии и ачивки.
type делит дисциплины на силовые/кардио/навыковые (валидируется на CRUD, S3.1).
exercise — конкретное упражнение внутри вида спорта (FK sport_id); на него ссылаются
подходы/логи/рекорды. kind отделяет силовое/кардио/навык, unit — дефолтная единица.
"""

from enum import StrEnum

from sqlmodel import Field, SQLModel


class SportCategory(StrEnum):
    """Таксономия дисциплин M1 — на неё переезжает каталог sport (M1·B13).

    Заводится сейчас как основа; перевод поля Sport.type, API, фронта и данных
    на эти категории — отдельные карточки M1. До тех пор активен legacy-алиас
    SportType (strength/cardio/skill), которым пользуется существующий код.
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


class SportType(StrEnum):
    """Временный legacy-алиас (M1·B13): старая тройка типов дисциплины.

    Ещё используется каталогом sport, API (/sports), фронтом и данными — будет
    заменён на SportCategory, когда соответствующие карточки M1 мигрируют значения.
    """

    strength = "strength"
    cardio = "cardio"
    skill = "skill"


class Sport(SQLModel, table=True):
    __tablename__ = "sport"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    type: SportType
    description: str | None = None


class Exercise(SQLModel, table=True):
    __tablename__ = "exercise"

    id: int | None = Field(default=None, primary_key=True)
    sport_id: int = Field(foreign_key="sport.id", index=True)
    name: str
    kind: str | None = None  # strength | cardio | skill — как логировать упражнение
    unit: str | None = None  # дефолтная единица: кг / повторы / сек / км
    notes: str | None = None  # произвольная заметка (техника, хват, оговорки) — S3.2
