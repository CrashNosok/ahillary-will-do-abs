"""Челлендж (M6·B30) и участие в нём (M6·B31).

Challenge — задание/вызов по виду спорта, который заводят пользователи: привязан
к дисциплине через FK sport_id и к автору через FK creator_user_id (оба NOT NULL,
индексированы). title и description обязательны; is_base отделяет базовые
(встроенные) челленджи от пользовательских (bool, дефолт False, как Sport.is_global).

ChallengeParticipant — связка «пользователь ↔ челлендж»: кто в каком вызове участвует
и в каком он статусе. unique (challenge_id, user_id): один пользователь участвует в
челлендже не более одного раза. Роутера/UI у обеих моделей пока нет (только модель).
"""

from enum import StrEnum

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class Challenge(SQLModel, table=True):
    __tablename__ = "challenge"

    id: int | None = Field(default=None, primary_key=True)
    sport_id: int = Field(foreign_key="sport.id", index=True)
    creator_user_id: int = Field(foreign_key="user.id", index=True)  # автор челленджа
    title: str  # заголовок вызова, обязателен
    description: str  # что нужно сделать, обязательно
    is_base: bool = Field(default=False)  # базовый (встроенный) vs пользовательский


class ChallengeParticipantStatus(StrEnum):
    active = "active"  # участвует прямо сейчас
    completed = "completed"  # довёл вызов до конца
    abandoned = "abandoned"  # бросил


class ChallengeParticipant(SQLModel, table=True):
    __tablename__ = "challenge_participant"
    __table_args__ = (
        # Пользователь участвует в челлендже максимум один раз — повторный join упрётся
        # в unique (а не создаст дубль). Своя пара констрейнтов, как у sport_level.
        UniqueConstraint("challenge_id", "user_id", name="uq_challenge_participant_challenge_user"),
    )

    id: int | None = Field(default=None, primary_key=True)
    challenge_id: int = Field(foreign_key="challenge.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    # Статус участия (см. ChallengeParticipantStatus); по умолчанию — active.
    status: str = Field(default=ChallengeParticipantStatus.active, index=True)
