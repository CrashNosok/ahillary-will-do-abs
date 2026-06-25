"""Модель sport_mentor (M5·B25): наставники/тренеры внутри вида спорта.

Закрывает критерии карточки: таблица sport_mentor(id, sport_id, name, bio, contact,
url, photo_path) с FK на sport.id. name обязателен; bio/contact/url/photo_path
необязательны (по умолчанию None).
"""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.models.sport import Sport, SportMentor


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Sport(name="Бокс", category="combat"))  # sport.id == 1
        s.commit()
        yield s


def test_create_sport_mentor_persists_all_fields(session):
    session.add(
        SportMentor(
            sport_id=1,
            name="Иван Тренеров",
            bio="МС по боксу, 10 лет стажа",
            contact="@ivan_coach",
            url="https://example.com/ivan",
            photo_path="data/mentors/ivan.jpg",
        )
    )
    session.commit()
    m = session.exec(select(SportMentor)).one()
    assert m.id is not None
    assert m.sport_id == 1
    assert m.name == "Иван Тренеров"
    assert m.bio == "МС по боксу, 10 лет стажа"
    assert m.contact == "@ivan_coach"
    assert m.url == "https://example.com/ivan"
    assert m.photo_path == "data/mentors/ivan.jpg"


def test_optional_fields_default_to_none(session):
    # Только обязательные поля: sport_id + name. Остальное — None по умолчанию.
    session.add(SportMentor(sport_id=1, name="Без анкеты"))
    session.commit()
    m = session.exec(select(SportMentor)).one()
    assert m.bio is None
    assert m.contact is None
    assert m.url is None
    assert m.photo_path is None


def test_mentor_requires_valid_sport_fk(session):
    # sport_id, которого нет в sport, нарушает внешний ключ.
    session.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
    session.add(SportMentor(sport_id=999, name="Призрак"))
    with pytest.raises(IntegrityError):
        session.commit()
