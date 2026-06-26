"""Сводка по видам спорта (sport_summary.summaries): глобальные счётчики + персональная
статистика; чужой прогресс не считается; прогресс живёт без связки (не сбрасывается при отвязке)."""

import datetime as dt

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401 — регистрирует таблицы в SQLModel.metadata
from app.models.achievement import Achievement
from app.models.sport import Sport, SportCategory, SportEvent, SportLevel
from app.models.user_sport import UserSport
from app.models.workout import WorkoutSession
from app.services.sport_summary import summaries


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _sport(session, name, category):
    sp = Sport(name=name, category=category)
    session.add(sp)
    session.commit()
    session.refresh(sp)
    return sp.id


def test_counts_global_and_personal(session):
    sid = _sport(session, "Бокс", SportCategory.combat)
    session.add(SportLevel(sport_id=sid, code="l1", label="Новичок", rank=1))
    session.add(SportEvent(sport_id=sid, title="Турнир", starts_on=dt.date(2026, 7, 1)))
    session.add(Achievement(user_id=1, sport_id=sid, title="a", status="unlocked"))
    session.add(Achievement(user_id=1, sport_id=sid, title="b", status="locked"))
    session.add(Achievement(user_id=2, sport_id=sid, title="c", status="unlocked"))  # чужая
    for _ in range(3):
        session.add(WorkoutSession(user_id=1, date=dt.date(2026, 6, 1), sport_id=sid))
    # привязка с уровнем
    lvl = SportLevel(sport_id=sid, code="l2", label="Любитель", rank=2)
    session.add(lvl)
    session.commit()
    session.add(UserSport(user_id=1, sport_id=sid, current_level_id=lvl.id))
    session.commit()

    s = summaries(session, user_id=1)[sid]
    assert s.levels == 2 and s.events == 1
    assert s.achievements_total == 2 and s.achievements_unlocked == 1  # чужая не в счёте
    assert s.workouts == 3
    assert s.linked is True and s.current_level == "Любитель"


def test_progress_persists_without_link(session):
    # прогресс (тренировки/ачивки) есть, а связки UserSport нет → вид в сводке, linked=False.
    sid = _sport(session, "Бег", SportCategory.endurance)
    session.add(WorkoutSession(user_id=1, date=dt.date(2026, 6, 1), sport_id=sid))
    session.add(Achievement(user_id=1, sport_id=sid, title="x", status="unlocked"))
    session.commit()

    s = summaries(session, user_id=1)
    assert sid in s
    assert s[sid].workouts == 1 and s[sid].achievements_unlocked == 1
    assert s[sid].linked is False and s[sid].current_level is None


def test_level_persists_after_soft_unlink(session):
    # Мягко отвязанная связка (linked=False) хранит уровень → linked=False, но current_level виден.
    sid = _sport(session, "Падел", SportCategory.racket)
    lvl = SportLevel(sport_id=sid, code="c", label="C", rank=3)
    session.add(lvl)
    session.commit()
    session.add(UserSport(user_id=1, sport_id=sid, current_level_id=lvl.id, linked=False))
    session.commit()

    s = summaries(session, user_id=1)[sid]
    assert s.linked is False and s.current_level == "C"
