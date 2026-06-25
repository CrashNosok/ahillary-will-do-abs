"""Сид базового челленджа WIPEOUTS (M7·B39): is_base для категории action, идемпотентно."""

from sqlmodel import Session, select

from app.core import db
from app.core.seed import (
    BASE_CHALLENGE_TITLE,
    seed_base_challenge,
    seed_sports,
    seed_user,
)
from app.models.challenge import Challenge
from app.models.sport import Sport, SportCategory


def _prepare_db(tmp_path, monkeypatch):
    # Движок направляем во временную папку, чтобы не трогать backend/data.
    monkeypatch.setattr(db, "engine", db.make_engine(tmp_path / "app.db"))
    db.init_db()


def test_seeds_base_wipeouts_for_action(tmp_path, monkeypatch):
    _prepare_db(tmp_path, monkeypatch)
    with Session(db.engine) as session:
        seed_user(session)
        seed_sports(session)
        created = seed_base_challenge(session)

    assert created is not None
    assert created.is_base is True
    assert created.title == BASE_CHALLENGE_TITLE

    with Session(db.engine) as session:
        challenge = session.exec(
            select(Challenge).where(Challenge.title == BASE_CHALLENGE_TITLE)
        ).one()
        sport = session.get(Sport, challenge.sport_id)

    # критерий карточки: базовый челлендж привязан к глобальной дисциплине категории action
    assert sport.category == SportCategory.action
    assert sport.is_global is True


def test_seed_base_challenge_is_idempotent(tmp_path, monkeypatch):
    _prepare_db(tmp_path, monkeypatch)
    with Session(db.engine) as session:
        seed_user(session)
        seed_sports(session)
        seed_base_challenge(session)
        again = seed_base_challenge(session)  # повторный старт

    assert again is None  # повтор не создаёт второй WIPEOUTS

    with Session(db.engine) as session:
        rows = session.exec(select(Challenge).where(Challenge.title == BASE_CHALLENGE_TITLE)).all()
    assert len(rows) == 1  # единственность держится в сервисе


def test_seed_base_challenge_needs_action_sport(tmp_path, monkeypatch):
    # Юзер есть, но каталог дисциплин пуст — челленджу не на что опереться (sport_id), пропускаем.
    _prepare_db(tmp_path, monkeypatch)
    with Session(db.engine) as session:
        seed_user(session)
        created = seed_base_challenge(session)

    assert created is None
    with Session(db.engine) as session:
        assert session.exec(select(Challenge)).all() == []


def test_seed_base_challenge_needs_user(tmp_path, monkeypatch):
    # Дисциплины есть, но юзера нет — у челленджа обязателен автор (creator_user_id), пропускаем.
    _prepare_db(tmp_path, monkeypatch)
    with Session(db.engine) as session:
        seed_sports(session)
        created = seed_base_challenge(session)

    assert created is None
    with Session(db.engine) as session:
        assert session.exec(select(Challenge)).all() == []
