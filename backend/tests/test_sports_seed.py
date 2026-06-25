"""Сид базового каталога дисциплин (M7·B37): 5 спортов по категориям, идемпотентно."""

from sqlmodel import Session, select

from app.core import db
from app.core.seed import BASE_SPORTS, seed_sports
from app.models.sport import Sport, SportCategory


def _prepare_db(tmp_path, monkeypatch):
    # Движок направляем во временную папку, чтобы не трогать backend/data.
    monkeypatch.setattr(db, "engine", db.make_engine(tmp_path / "app.db"))
    db.init_db()


def test_seed_creates_five_sports_by_category(tmp_path, monkeypatch):
    _prepare_db(tmp_path, monkeypatch)

    with Session(db.engine) as session:
        added = seed_sports(session)

    assert added == 5  # критерий: 5 спортов

    with Session(db.engine) as session:
        sports = session.exec(select(Sport).order_by(Sport.name)).all()
        by_name = {s.name: s for s in sports}

    assert len(sports) == 5
    # критерий: категории зал=strength, кайт/эндуро/вейк=action, падел=racket
    assert by_name["Зал"].category == SportCategory.strength
    assert by_name["Кайт"].category == SportCategory.action
    assert by_name["Эндуро"].category == SportCategory.action
    assert by_name["Вейк"].category == SportCategory.action
    assert by_name["Падел"].category == SportCategory.racket
    # встроенные дисциплины помечены is_global
    assert all(s.is_global for s in sports)


def test_seed_is_idempotent_no_duplicates(tmp_path, monkeypatch):
    _prepare_db(tmp_path, monkeypatch)

    with Session(db.engine) as session:
        seed_sports(session)
    with Session(db.engine) as session:
        added_again = seed_sports(session)  # повторный старт

    assert added_again == 0  # критерий: повтор ничего не добавляет

    with Session(db.engine) as session:
        names = session.exec(select(Sport.name)).all()
    assert len(names) == len(BASE_SPORTS)  # критерий: дублей нет
    assert len(set(names)) == len(names)


def test_seed_keeps_existing_sports_and_fills_gaps(tmp_path, monkeypatch):
    # Каталог не пуст, часть базовых дисциплин заведена вручную — сид добавляет лишь недостающие.
    _prepare_db(tmp_path, monkeypatch)
    with Session(db.engine) as session:
        session.add(Sport(name="Зал", category=SportCategory.strength))
        session.add(Sport(name="Бег", category=SportCategory.endurance))
        session.commit()

    with Session(db.engine) as session:
        added = seed_sports(session)

    assert added == 4  # «Зал» уже есть — добавились только Кайт/Эндуро/Вейк/Падел

    with Session(db.engine) as session:
        names = session.exec(select(Sport.name)).all()
    assert sorted(names) == sorted(["Бег", "Зал", "Кайт", "Эндуро", "Вейк", "Падел"])
