"""Модель challenge_sponsor (M6·B33): спонсорство челленджа.

Закрывает критерии карточки: таблица challenge_sponsor(id, challenge_id,
sponsor_id, amount, currency) с FK challenge_id на challenge.id и sponsor_id на
sponsor.id; amount хранится как Decimal (без потери копеек); unique
(challenge_id, sponsor_id) — спонсор поддерживает челлендж не более одного раза.
"""

from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.models.challenge import Challenge, ChallengeSponsor
from app.models.sponsor import Sponsor
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
        s.add(Sponsor(name="Acme"))  # sponsor.id == 1
        s.commit()
        s.add(
            Challenge(
                sport_id=1, creator_user_id=1, title="30 дней планки", description="Держи планку."
            )
        )  # challenge.id == 1
        s.commit()
        yield s


def test_create_sponsor_persists_all_fields(session):
    session.add(
        ChallengeSponsor(challenge_id=1, sponsor_id=1, amount=Decimal("150.50"), currency="USD")
    )
    session.commit()
    cs = session.exec(select(ChallengeSponsor)).one()
    assert cs.id is not None
    assert cs.challenge_id == 1
    assert cs.sponsor_id == 1
    assert cs.amount == Decimal("150.50")  # копейки на месте, не float
    assert cs.currency == "USD"


def test_duplicate_sponsorship_violates_unique(session):
    # Один спонсор не может поддержать один челлендж дважды.
    session.add(
        ChallengeSponsor(challenge_id=1, sponsor_id=1, amount=Decimal("10"), currency="USD")
    )
    session.commit()
    session.add(
        ChallengeSponsor(challenge_id=1, sponsor_id=1, amount=Decimal("20"), currency="EUR")
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_sponsor_requires_valid_challenge_fk(session):
    # challenge_id, которого нет в challenge, нарушает внешний ключ.
    session.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
    session.add(
        ChallengeSponsor(challenge_id=999, sponsor_id=1, amount=Decimal("10"), currency="USD")
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_sponsor_requires_valid_sponsor_fk(session):
    # sponsor_id, которого нет в sponsor, нарушает внешний ключ.
    session.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
    session.add(
        ChallengeSponsor(challenge_id=1, sponsor_id=999, amount=Decimal("10"), currency="USD")
    )
    with pytest.raises(IntegrityError):
        session.commit()
