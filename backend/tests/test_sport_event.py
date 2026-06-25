"""Модель sport_event (M5·B24): события/соревнования внутри вида спорта.

Закрывает критерии карточки: таблица sport_event(id, sport_id, title, description,
location, starts_on, ends_on, url) с FK на sport.id. title и starts_on обязательны;
описание/место/ends_on/url необязательны (по умолчанию None).
"""

import datetime as dt

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.models.sport import Sport, SportEvent


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
        yield s


def test_create_sport_event_persists_all_fields(session):
    session.add(
        SportEvent(
            sport_id=1,
            title="Московский марафон",
            description="42.2 км по центру",
            location="Москва",
            starts_on=dt.date(2026, 9, 20),
            ends_on=dt.date(2026, 9, 20),
            url="https://moscowmarathon.org",
        )
    )
    session.commit()
    ev = session.exec(select(SportEvent)).one()
    assert ev.id is not None
    assert ev.sport_id == 1
    assert ev.title == "Московский марафон"
    assert ev.description == "42.2 км по центру"
    assert ev.location == "Москва"
    assert ev.starts_on == dt.date(2026, 9, 20)
    assert ev.ends_on == dt.date(2026, 9, 20)
    assert ev.url == "https://moscowmarathon.org"


def test_optional_fields_default_to_none(session):
    # Только обязательные поля: title + starts_on. Остальное — None по умолчанию.
    session.add(SportEvent(sport_id=1, title="Открытый старт", starts_on=dt.date(2026, 5, 1)))
    session.commit()
    ev = session.exec(select(SportEvent)).one()
    assert ev.description is None
    assert ev.location is None
    assert ev.ends_on is None
    assert ev.url is None


def test_multi_day_event_keeps_distinct_dates(session):
    session.add(
        SportEvent(
            sport_id=1,
            title="Сборы",
            starts_on=dt.date(2026, 7, 1),
            ends_on=dt.date(2026, 7, 14),
        )
    )
    session.commit()
    ev = session.exec(select(SportEvent)).one()
    assert ev.starts_on == dt.date(2026, 7, 1)
    assert ev.ends_on == dt.date(2026, 7, 14)


def test_event_requires_valid_sport_fk(session):
    # sport_id, которого нет в sport, нарушает внешний ключ.
    session.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
    session.add(SportEvent(sport_id=999, title="Призрак", starts_on=dt.date(2026, 1, 1)))
    with pytest.raises(IntegrityError):
        session.commit()
