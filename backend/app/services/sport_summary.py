"""Сводка по видам спорта — для карточек каталога и «Мои виды спорта».

Глобальные счётчики (одинаковы для всех): ступени, события, наставники, челленджи.
Персональная статистика пользователя: ачивок выполнено/всего, текущий уровень, число тренировок,
привязан ли вид. Прогресс (ачивки/тренировки) — у пользователя (Achievement.user_id /
WorkoutSession.user_id), НЕ на связке UserSport, поэтому при отвязке не сбрасывается и продолжает
показываться. Возвращаем словарь только для видов, у которых есть хоть какие-то данные — фронт
дефолтит остальные нулями.
"""

from dataclasses import dataclass

from sqlalchemy import func
from sqlmodel import Session, select

from app.models.achievement import Achievement
from app.models.challenge import Challenge
from app.models.sport import SportEvent, SportLevel, SportMentor
from app.models.user_sport import UserSport
from app.models.workout import WorkoutSession


@dataclass(frozen=True)
class SportSummary:
    sport_id: int
    # глобальное (одинаково для всех пользователей):
    levels: int
    events: int
    mentors: int
    challenges: int
    # персональное (текущий пользователь):
    achievements_total: int
    achievements_unlocked: int
    workouts: int
    current_level: str | None
    linked: bool


def _counts(session: Session, sport_col, *where) -> dict[int, int]:
    """sport_id → count для модели (group by sport_id; опц. доп. условия фильтра)."""
    stmt = select(sport_col, func.count()).where(*where).group_by(sport_col)
    return {sid: n for sid, n in session.exec(stmt).all() if sid is not None}


def summaries(session: Session, user_id: int) -> dict[int, SportSummary]:
    """sport_id → SportSummary для видов, у которых есть данные (глобальные или у пользователя)."""
    levels = _counts(session, SportLevel.sport_id)
    events = _counts(session, SportEvent.sport_id)
    mentors = _counts(session, SportMentor.sport_id)
    challenges = _counts(session, Challenge.sport_id)
    ach_total = _counts(session, Achievement.sport_id, Achievement.user_id == user_id)
    ach_unlocked = _counts(
        session,
        Achievement.sport_id,
        Achievement.user_id == user_id,
        Achievement.status == "unlocked",
    )
    workouts = _counts(session, WorkoutSession.sport_id, WorkoutSession.user_id == user_id)

    # Связки пользователя. linked_ids — только АКТИВНЫЕ (linked=True): по ним рисуется «привязан».
    # Уровень берём со связки в т.ч. ОТВЯЗАННОЙ (мягкая отвязка) — он не сбрасывается.
    links = session.exec(select(UserSport).where(UserSport.user_id == user_id)).all()
    linked_ids = {link.sport_id for link in links if link.linked}
    all_link_ids = {link.sport_id for link in links}
    level_id_by_sport = {
        link.sport_id: link.current_level_id for link in links if link.current_level_id is not None
    }
    label_by_level_id: dict[int, str] = {}
    if level_id_by_sport:
        rows = session.exec(
            select(SportLevel.id, SportLevel.label).where(
                SportLevel.id.in_(level_id_by_sport.values())
            )
        ).all()
        label_by_level_id = {lid: label for lid, label in rows}

    sport_ids = (
        set(levels)
        | set(events)
        | set(mentors)
        | set(challenges)
        | set(ach_total)
        | set(workouts)
        | all_link_ids
    )
    out: dict[int, SportSummary] = {}
    for sid in sport_ids:
        level_id = level_id_by_sport.get(sid)
        out[sid] = SportSummary(
            sport_id=sid,
            levels=levels.get(sid, 0),
            events=events.get(sid, 0),
            mentors=mentors.get(sid, 0),
            challenges=challenges.get(sid, 0),
            achievements_total=ach_total.get(sid, 0),
            achievements_unlocked=ach_unlocked.get(sid, 0),
            workouts=workouts.get(sid, 0),
            current_level=label_by_level_id.get(level_id) if level_id is not None else None,
            linked=sid in linked_ids,
        )
    return out
