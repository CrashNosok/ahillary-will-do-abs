"""Модель sport_recommendation (M5·B26): рекомендации/гайды внутри вида спорта.

Закрывает критерии карточки: таблица sport_recommendation(id, sport_id,
from_level_id, to_level_id, title, body) с FK sport_id на sport.id и
необязательными FK from_level_id/to_level_id на sport_level.id. title и body
обязательны; from_level_id/to_level_id по умолчанию None.
"""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.models.sport import Sport, SportLevel, SportRecommendation


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
        s.commit()
        # Две ступени для проверки FK from/to_level_id.
        s.add(SportLevel(sport_id=1, code="beginner", label="Новичок", rank=1))
        s.add(SportLevel(sport_id=1, code="amateur", label="Любитель", rank=2))
        s.commit()
        yield s


def test_create_recommendation_persists_all_fields(session):
    session.add(
        SportRecommendation(
            sport_id=1,
            from_level_id=1,
            to_level_id=2,
            title="С новичка до любителя",
            body="Бегайте 3 раза в неделю, добавляйте по 10% объёма.",
        )
    )
    session.commit()
    r = session.exec(select(SportRecommendation)).one()
    assert r.id is not None
    assert r.sport_id == 1
    assert r.from_level_id == 1
    assert r.to_level_id == 2
    assert r.title == "С новичка до любителя"
    assert r.body == "Бегайте 3 раза в неделю, добавляйте по 10% объёма."


def test_level_ids_default_to_none(session):
    # Обязательны только sport_id + title + body; уровни — None по умолчанию.
    session.add(SportRecommendation(sport_id=1, title="Общий совет", body="Разминайтесь."))
    session.commit()
    r = session.exec(select(SportRecommendation)).one()
    assert r.from_level_id is None
    assert r.to_level_id is None


def test_recommendation_requires_valid_sport_fk(session):
    # sport_id, которого нет в sport, нарушает внешний ключ.
    session.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
    session.add(SportRecommendation(sport_id=999, title="Призрак", body="..."))
    with pytest.raises(IntegrityError):
        session.commit()


def test_recommendation_requires_valid_level_fk(session):
    # from_level_id, которого нет в sport_level, нарушает внешний ключ.
    session.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
    session.add(
        SportRecommendation(sport_id=1, from_level_id=999, title="Битый уровень", body="...")
    )
    with pytest.raises(IntegrityError):
        session.commit()
