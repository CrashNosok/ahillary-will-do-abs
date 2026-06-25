"""Каталог тренировок (S1.2/S3.1): вид спорта и упражнение.

sport — дисциплина (калистеника, бег, силовая…); на неё ссылаются сессии и ачивки.
category делит дисциплины по таксономии M1 (валидируется на CRUD, S3.1).
exercise — конкретное упражнение внутри вида спорта (FK sport_id); на него ссылаются
подходы/логи/рекорды. kind отделяет силовое/кардио/навык, unit — дефолтная единица.
"""

import datetime as dt
from enum import StrEnum

from sqlalchemy import UniqueConstraint
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


class SportLevel(SQLModel, table=True):
    """Уровень/грейд внутри вида спорта (M5·B23): ступени прогресса по дисциплине.

    code — машинный код ступени (напр. "beginner", "L1"), label — подпись для UI,
    rank — порядок ступени в дисциплине (целое, 1 — низшая). На уровень опирается
    UserSport.current_level_id (пока nullable int без FK). Уровни одной дисциплины
    уникальны и по rank, и по code; разные дисциплины их не делят.
    """

    __tablename__ = "sport_level"
    __table_args__ = (
        UniqueConstraint("sport_id", "rank", name="uq_sport_level_sport_rank"),
        UniqueConstraint("sport_id", "code", name="uq_sport_level_sport_code"),
    )

    id: int | None = Field(default=None, primary_key=True)
    sport_id: int = Field(foreign_key="sport.id", index=True)
    code: str  # машинный код ступени, уникален в пределах спорта
    label: str  # человеко-читаемая подпись ступени (S3.x)
    rank: int  # порядок ступени в дисциплине, уникален в пределах спорта
    description: str | None = None  # развёрнутое описание требований ступени


class SportEvent(SQLModel, table=True):
    """Событие/соревнование по виду спорта (M5·B24): забег, турнир, сбор и т.п.

    Привязано к дисциплине через FK sport_id. title — обязательное название события,
    starts_on — дата начала (обязательна). ends_on — дата конца (None для однодневных),
    description/location/url — необязательные детали (анонс, место проведения, ссылка).
    Глобальный каталог без user-скоупа — как и sport/sport_level. Роутера пока нет.
    """

    __tablename__ = "sport_event"

    id: int | None = Field(default=None, primary_key=True)
    sport_id: int = Field(foreign_key="sport.id", index=True)
    title: str  # название события, обязательно
    description: str | None = None  # анонс/подробности
    location: str | None = None  # место проведения
    starts_on: dt.date  # дата начала, обязательна
    ends_on: dt.date | None = None  # дата конца; None — однодневное событие
    url: str | None = None  # ссылка на страницу события/регистрацию


class Exercise(SQLModel, table=True):
    __tablename__ = "exercise"

    id: int | None = Field(default=None, primary_key=True)
    sport_id: int = Field(foreign_key="sport.id", index=True)
    name: str
    kind: str | None = None  # strength | cardio | skill — как логировать упражнение
    unit: str | None = None  # дефолтная единица: кг / повторы / сек / км
    notes: str | None = None  # произвольная заметка (техника, хват, оговорки) — S3.2
