"""Челлендж (M6·B30), участие (M6·B31), видео-пруф (M6·B32) и спонсорство (M6·B33).

Challenge — задание/вызов по виду спорта, который заводят пользователи: привязан
к дисциплине через FK sport_id и к автору через FK creator_user_id (оба NOT NULL,
индексированы). title и description обязательны; is_base отделяет базовые
(встроенные) челленджи от пользовательских (bool, дефолт False, как Sport.is_global).

ChallengeParticipant — связка «пользователь ↔ челлендж»: кто в каком вызове участвует
и в каком он статусе. unique (challenge_id, user_id): один пользователь участвует в
челлендже не более одного раза.

ChallengeProof — видео-пруф участия (клон achievement_proof по participant_id): FK на
challenge_participant.id; в БД только пути к видео и превью на диске + uploaded_at и
notes. Роутера/UI у моделей пока нет (только модель + сервис).

ChallengeSponsor — связка «спонсор ↔ челлендж» с суммой поддержки: FK challenge_id и
sponsor_id (оба NOT NULL, индексированы). amount — Decimal(12,2), не float (деньги);
currency — код валюты (ISO 4217), обязателен и без дефолта, чтобы валюта не угадывалась
молча. unique (challenge_id, sponsor_id): спонсор поддерживает челлендж не более раза.
"""

import datetime as dt
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models._time import utcnow


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


class ChallengeProof(SQLModel, table=True):
    __tablename__ = "challenge_proof"

    id: int | None = Field(default=None, primary_key=True)
    participant_id: int = Field(foreign_key="challenge_participant.id", index=True)
    video_path: str | None = None  # путь к видео на диске (файл вне БД)
    thumbnail_path: str | None = None  # путь к превью на диске
    uploaded_at: dt.datetime = Field(default_factory=utcnow)
    notes: str | None = None


class ChallengeSponsor(SQLModel, table=True):
    __tablename__ = "challenge_sponsor"
    __table_args__ = (
        # Спонсор поддерживает один челлендж не более раза — повторная привязка упрётся
        # в unique. Та же пара констрейнтов, что у challenge_participant.
        UniqueConstraint(
            "challenge_id", "sponsor_id", name="uq_challenge_sponsor_challenge_sponsor"
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    challenge_id: int = Field(foreign_key="challenge.id", index=True)
    sponsor_id: int = Field(foreign_key="sponsor.id", index=True)
    # Сумма спонсорства — Decimal, не float (деньги не теряют копейки на округлении).
    amount: Decimal = Field(max_digits=12, decimal_places=2)
    currency: str  # код валюты (ISO 4217), обязателен и без дефолта — не угадываем
