"""Модель challenge (M6·B30): задания/вызовы по виду спорта.

Закрывает критерии карточки: таблица challenge(id, sport_id, creator_user_id,
title, description, is_base) с FK sport_id на sport.id и creator_user_id на
user.id. title/description обязательны; is_base — bool с дефолтом False.
"""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.models.challenge import Challenge
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
        yield s


def test_create_challenge_persists_all_fields(session):
    session.add(
        Challenge(
            sport_id=1,
            creator_user_id=1,
            title="30 дней планки",
            description="Каждый день держи планку на 10 секунд дольше.",
            is_base=True,
        )
    )
    session.commit()
    c = session.exec(select(Challenge)).one()
    assert c.id is not None
    assert c.sport_id == 1
    assert c.creator_user_id == 1
    assert c.title == "30 дней планки"
    assert c.description == "Каждый день держи планку на 10 секунд дольше."
    assert c.is_base is True


def test_is_base_defaults_to_false(session):
    # Обязательны sport_id + creator_user_id + title + description; is_base → False.
    session.add(
        Challenge(sport_id=1, creator_user_id=1, title="Свой вызов", description="Пробеги 5 км.")
    )
    session.commit()
    c = session.exec(select(Challenge)).one()
    assert c.is_base is False


def test_challenge_requires_valid_sport_fk(session):
    # sport_id, которого нет в sport, нарушает внешний ключ.
    session.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
    session.add(Challenge(sport_id=999, creator_user_id=1, title="Призрак", description="..."))
    with pytest.raises(IntegrityError):
        session.commit()


def test_challenge_requires_valid_creator_fk(session):
    # creator_user_id, которого нет в user, нарушает внешний ключ.
    session.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
    session.add(Challenge(sport_id=1, creator_user_id=999, title="Битый автор", description="..."))
    with pytest.raises(IntegrityError):
        session.commit()
