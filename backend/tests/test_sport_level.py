"""Модель sport_level (M5·B23): уровни/грейды дисциплины внутри вида спорта.

Закрывает критерии карточки: таблица sport_level(id, sport_id, code, label, rank,
description) с составными уникальными ограничениями (sport_id, rank) и (sport_id, code).
Уровни одного спорта не дублируются по rank и по code; разные спорты их не делят.
"""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.models.sport import Sport, SportLevel


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Sport(name="Калистеника", category="strength"))  # sport.id == 1
        s.add(Sport(name="Бег", category="endurance"))  # sport.id == 2
        s.commit()
        yield s


def _level(sport_id: int, code: str, rank: int, label: str = "Уровень") -> SportLevel:
    return SportLevel(sport_id=sport_id, code=code, label=label, rank=rank)


def test_create_sport_level_persists_fields(session):
    session.add(
        SportLevel(
            sport_id=1, code="beginner", label="Начальный", rank=1, description="Базовые элементы"
        )
    )
    session.commit()
    lvl = session.exec(select(SportLevel)).one()
    assert lvl.id is not None
    assert lvl.sport_id == 1
    assert lvl.code == "beginner"
    assert lvl.label == "Начальный"
    assert lvl.rank == 1
    assert lvl.description == "Базовые элементы"


def test_duplicate_rank_within_sport_rejected(session):
    session.add(_level(1, "beginner", 1))
    session.commit()
    session.add(_level(1, "intermediate", 1))  # тот же (sport_id, rank)
    with pytest.raises(IntegrityError):
        session.commit()


def test_duplicate_code_within_sport_rejected(session):
    session.add(_level(1, "beginner", 1))
    session.commit()
    session.add(_level(1, "beginner", 2))  # тот же (sport_id, code)
    with pytest.raises(IntegrityError):
        session.commit()


def test_same_rank_and_code_across_sports_allowed(session):
    session.add(_level(1, "beginner", 1))
    session.add(_level(2, "beginner", 1))  # другой sport_id — коллизии нет
    session.commit()
    assert len(session.exec(select(SportLevel)).all()) == 2
