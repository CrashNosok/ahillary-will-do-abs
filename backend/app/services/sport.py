"""Сводка по виду спорта (M5·B27): агрегат каталога дисциплины для одного экрана.

sport_overview собирает в один DTO всё, что навешано на вид спорта: ступени
(SportLevel), события (SportEvent), наставников (SportMentor) и рекомендации
(SportRecommendation) — это глобальный каталог без user-скоупа, отдаём упорядоченно
для стабильного UI — плюс счётчик ачивок владельца по дисциплине (achievement
скоупится по user_id, M0·B6: чужие ачивки в счёт не идут).
"""

from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, select

from app.models.achievement import Achievement
from app.models.sport import (
    Sport,
    SportEvent,
    SportLevel,
    SportMentor,
    SportRecommendation,
)


class SportOverview(BaseModel):
    """DTO экрана дисциплины: сам вид спорта + его каталог + счётчик ачивок юзера."""

    sport: Sport
    levels: list[SportLevel]
    events: list[SportEvent]
    mentors: list[SportMentor]
    recommendations: list[SportRecommendation]
    achievement_count: int


def sport_overview(session: Session, sport: Sport, *, user_id: int) -> SportOverview:
    """Сводка по дисциплине: ступени/события/менторы/рекомендации + число ачивок владельца.

    Каталожные таблицы глобальны — отдаём как есть, упорядочивая для предсказуемого UI
    (уровни по rank, события по дате старта, менторы по имени, рекомендации по id).
    achievement_count — COUNT(*) ачивок дисциплины со скоупом по user_id.
    """
    levels = session.exec(
        select(SportLevel).where(SportLevel.sport_id == sport.id).order_by(SportLevel.rank)
    ).all()
    events = session.exec(
        select(SportEvent).where(SportEvent.sport_id == sport.id).order_by(SportEvent.starts_on)
    ).all()
    mentors = session.exec(
        select(SportMentor).where(SportMentor.sport_id == sport.id).order_by(SportMentor.name)
    ).all()
    recommendations = session.exec(
        select(SportRecommendation)
        .where(SportRecommendation.sport_id == sport.id)
        .order_by(SportRecommendation.id)
    ).all()
    achievement_count = session.exec(
        select(func.count())
        .select_from(Achievement)
        .where(Achievement.sport_id == sport.id, Achievement.user_id == user_id)
    ).one()
    return SportOverview(
        sport=sport,
        levels=list(levels),
        events=list(events),
        mentors=list(mentors),
        recommendations=list(recommendations),
        achievement_count=achievement_count,
    )
