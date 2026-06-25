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


# Секции каталога дисциплины (M5·B28). Порядок задан здесь один раз и переиспользуется
# и сводкой /overview, и отдельными список-эндпоинтами /sports/{id}/<секция> — чтобы UI
# видел одинаковую сортировку в обоих местах. Каталог глобален (без user-скоупа).


def list_levels(session: Session, sport_id: int) -> list[SportLevel]:
    """Ступени дисциплины по возрастанию rank (1 — низшая)."""
    return list(
        session.exec(
            select(SportLevel).where(SportLevel.sport_id == sport_id).order_by(SportLevel.rank)
        ).all()
    )


def list_events(session: Session, sport_id: int) -> list[SportEvent]:
    """События дисциплины по дате старта (ближайшие раньше)."""
    return list(
        session.exec(
            select(SportEvent).where(SportEvent.sport_id == sport_id).order_by(SportEvent.starts_on)
        ).all()
    )


def list_mentors(session: Session, sport_id: int) -> list[SportMentor]:
    """Наставники дисциплины по имени (алфавит)."""
    return list(
        session.exec(
            select(SportMentor).where(SportMentor.sport_id == sport_id).order_by(SportMentor.name)
        ).all()
    )


def list_recommendations(session: Session, sport_id: int) -> list[SportRecommendation]:
    """Рекомендации дисциплины в порядке создания (по id)."""
    return list(
        session.exec(
            select(SportRecommendation)
            .where(SportRecommendation.sport_id == sport_id)
            .order_by(SportRecommendation.id)
        ).all()
    )


def sport_overview(session: Session, sport: Sport, *, user_id: int) -> SportOverview:
    """Сводка по дисциплине: ступени/события/менторы/рекомендации + число ачивок владельца.

    Секции каталога глобальны — отдаём упорядоченно теми же хелперами, что и список-эндпоинты
    (B28), чтобы порядок совпадал. achievement_count — COUNT(*) ачивок дисциплины по user_id.
    """
    achievement_count = session.exec(
        select(func.count())
        .select_from(Achievement)
        .where(Achievement.sport_id == sport.id, Achievement.user_id == user_id)
    ).one()
    return SportOverview(
        sport=sport,
        levels=list_levels(session, sport.id),
        events=list_events(session, sport.id),
        mentors=list_mentors(session, sport.id),
        recommendations=list_recommendations(session, sport.id),
        achievement_count=achievement_count,
    )
