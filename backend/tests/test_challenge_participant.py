"""Модель challenge_participant (M6·B31): участие пользователя в челлендже.

Закрывает критерии карточки: таблица challenge_participant(id, challenge_id,
user_id, status) с FK challenge_id на challenge.id и user_id на user.id; status
по умолчанию "active"; unique (challenge_id, user_id) — пользователь участвует в
челлендже не более одного раза.
"""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.models.challenge import (
    Challenge,
    ChallengeParticipant,
    ChallengeParticipantStatus,
)
from app.models.sport import Sport
from app.models.user import User


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Sport(name="Бег", category="endurance"))  # sport.id == 1
        s.add(User(email="me@example.com", password_hash="h"))  # user.id == 1
        s.commit()
        s.add(
            Challenge(
                sport_id=1, creator_user_id=1, title="30 дней планки", description="Держи планку."
            )
        )  # challenge.id == 1
        s.commit()
        yield s


def test_create_participant_persists_all_fields(session):
    session.add(
        ChallengeParticipant(challenge_id=1, user_id=1, status=ChallengeParticipantStatus.completed)
    )
    session.commit()
    p = session.exec(select(ChallengeParticipant)).one()
    assert p.id is not None
    assert p.challenge_id == 1
    assert p.user_id == 1
    assert p.status == "completed"


def test_status_defaults_to_active(session):
    # Обязательны challenge_id + user_id; status → "active".
    session.add(ChallengeParticipant(challenge_id=1, user_id=1))
    session.commit()
    p = session.exec(select(ChallengeParticipant)).one()
    assert p.status == ChallengeParticipantStatus.active


def test_duplicate_participation_violates_unique(session):
    # Один пользователь не может вступить в один челлендж дважды.
    session.add(ChallengeParticipant(challenge_id=1, user_id=1))
    session.commit()
    session.add(ChallengeParticipant(challenge_id=1, user_id=1))
    with pytest.raises(IntegrityError):
        session.commit()


def test_participant_requires_valid_challenge_fk(session):
    # challenge_id, которого нет в challenge, нарушает внешний ключ.
    session.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
    session.add(ChallengeParticipant(challenge_id=999, user_id=1))
    with pytest.raises(IntegrityError):
        session.commit()


def test_participant_requires_valid_user_fk(session):
    # user_id, которого нет в user, нарушает внешний ключ.
    session.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
    session.add(ChallengeParticipant(challenge_id=1, user_id=999))
    with pytest.raises(IntegrityError):
        session.commit()
