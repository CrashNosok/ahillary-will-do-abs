"""CRUD виды спорта (S3.1).

Пользователь заводит дисциплины: sport(name, category, description). category валидируется
схемой запроса (таксономия SportCategory M1·B14 → иначе 422). name уникален — повтор отдаёт 409.
Все роуты под сессией (CurrentUser) — приложение однопользовательское.
"""

import datetime as dt
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.models.achievement import Achievement, AchievementProof
from app.models.sport import (
    Sport,
    SportCategory,
    SportEvent,
    SportLevel,
    SportMentor,
    SportRecommendation,
    SportSuggestion,
)
from app.services import achievement as achievement_service
from app.services import sport as sport_service
from app.services.achievement_schema import AthleteLevel, InvalidAchievementSetError
from app.services.llm import LLMError

router = APIRouter(prefix="/sports", tags=["sports"])

SessionDep = Annotated[Session, Depends(get_session)]


class SportCreate(BaseModel):
    name: str
    category: SportCategory
    description: str | None = None
    long_description: str | None = None
    is_global: bool = False


class SportUpdate(BaseModel):
    name: str | None = None
    category: SportCategory | None = None
    description: str | None = None
    long_description: str | None = None
    is_global: bool | None = None


class AchievementRead(BaseModel):
    """Ачивка для UI (S5.6): поля модели + has_proof — есть ли видео-пруф (рисовать превью)."""

    id: int
    sport_id: int | None
    title: str
    description: str | None
    level: str | None
    status: str
    created_at: dt.datetime
    unlocked_at: dt.datetime | None
    has_proof: bool


def slugify(value: str) -> str:
    """ЧПУ-слаг из названия: нижний регистр, пробелы → дефис, прочая пунктуация убрана.

    \\w (re.UNICODE) сохраняет буквы и для кириллицы ("Бег" → "бег"), поэтому слаг не пустеет
    на русских названиях. Пустой результат (название из одной пунктуации) → "sport".
    """
    text = re.sub(r"[^\w\s-]", "", value.strip().lower(), flags=re.UNICODE)
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return text or "sport"


def _unique_slug(session: Session, name: str) -> str:
    """Базовый слаг из name + суффикс -2, -3… при коллизии (slug уникален).

    ponytail: гонка между проверкой и commit игнорируется — приложение однопользовательское.
    """
    base = slugify(name)
    slug = base
    n = 2
    while session.exec(select(Sport).where(Sport.slug == slug)).first() is not None:
        slug = f"{base}-{n}"
        n += 1
    return slug


def _get_or_404(session: Session, sport_id: int) -> Sport:
    sport = session.get(Sport, sport_id)
    if sport is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Вид спорта не найден")
    return sport


def _commit_unique(session: Session, sport: Sport) -> Sport:
    """Сохраняет и переводит конфликт уникального name в 409 вместо 500."""
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Вид спорта с таким именем уже есть"
        ) from exc
    session.refresh(sport)
    return sport


@router.post("", status_code=status.HTTP_201_CREATED)
def create_sport(payload: SportCreate, session: SessionDep, _: CurrentUser) -> Sport:
    sport = Sport(**payload.model_dump())
    sport.slug = _unique_slug(session, sport.name)  # server-managed: стабильный, не из payload
    session.add(sport)
    return _commit_unique(session, sport)


@router.get("")
def list_sports(
    session: SessionDep,
    _: CurrentUser,
    category: Annotated[SportCategory | None, Query()] = None,
) -> list[Sport]:
    """Каталог дисциплин (S3.1). category= фильтрует по таксономии (M1·B15; вне неё → 422)."""
    stmt = select(Sport)
    if category is not None:
        stmt = stmt.where(Sport.category == category)
    return session.exec(stmt.order_by(Sport.name)).all()


@router.get("/categories")
def list_sport_categories(_: CurrentUser) -> list[SportCategory]:
    """Канонический список категорий дисциплин (таксономия M1·B15) — источник для фильтров UI.

    Объявлен ДО /{sport_id}, иначе "categories" попадёт в int-параметр пути и даст 422.
    """
    return list(SportCategory)


class SuggestionCreate(BaseModel):
    name: str
    category: SportCategory | None = None
    note: str | None = None


@router.post("/suggestions", status_code=status.HTTP_201_CREATED)
def create_suggestion(
    payload: SuggestionCreate, session: SessionDep, user: CurrentUser
) -> SportSuggestion:
    """«Предложить вид спорта» — заявка на ревью (status=pending). Пустое имя → 422.
    Объявлено ДО /{sport_id}, иначе "suggestions" уйдёт в int-параметр пути."""
    name = payload.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Укажите название вида спорта"
        )
    suggestion = SportSuggestion(
        user_id=user.id,
        name=name,
        category=payload.category,
        note=(payload.note or "").strip() or None,
    )
    session.add(suggestion)
    session.commit()
    session.refresh(suggestion)
    return suggestion


@router.get("/suggestions")
def list_suggestions(session: SessionDep, user: CurrentUser) -> list[SportSuggestion]:
    """Свои заявки (новые сверху). Скоуп по user_id — чужих не видно."""
    return session.exec(
        select(SportSuggestion)
        .where(SportSuggestion.user_id == user.id)
        .order_by(SportSuggestion.id.desc())
    ).all()


@router.get("/{sport_id}")
def get_sport(sport_id: int, session: SessionDep, _: CurrentUser) -> Sport:
    return _get_or_404(session, sport_id)


@router.patch("/{sport_id}")
def update_sport(sport_id: int, payload: SportUpdate, session: SessionDep, _: CurrentUser) -> Sport:
    sport = _get_or_404(session, sport_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(sport, key, value)
    session.add(sport)
    return _commit_unique(session, sport)


@router.delete("/{sport_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sport(sport_id: int, session: SessionDep, _: CurrentUser) -> None:
    sport = _get_or_404(session, sport_id)
    session.delete(sport)
    session.commit()


@router.get("/{sport_id}/overview")
def get_sport_overview(
    sport_id: int, session: SessionDep, user: CurrentUser
) -> sport_service.SportOverview:
    """Сводка по дисциплине (M5·B27): ступени, события, менторы, рекомендации + счётчик ачивок.

    Каталожные таблицы общие; achievement_count скоупится по владельцу (чужие не в счёте).
    404 — для неизвестного вида спорта.
    """
    sport = _get_or_404(session, sport_id)
    return sport_service.sport_overview(session, sport, user_id=user.id)


@router.get("/{sport_id}/levels")
def list_sport_levels(sport_id: int, session: SessionDep, _: CurrentUser) -> list[SportLevel]:
    """Ступени дисциплины по rank (M5·B28). 404 — для неизвестного вида спорта."""
    _get_or_404(session, sport_id)
    return sport_service.list_levels(session, sport_id)


@router.get("/{sport_id}/events")
def list_sport_events(sport_id: int, session: SessionDep, _: CurrentUser) -> list[SportEvent]:
    """События дисциплины по дате старта (M5·B28). 404 — для неизвестного вида спорта."""
    _get_or_404(session, sport_id)
    return sport_service.list_events(session, sport_id)


@router.get("/{sport_id}/mentors")
def list_sport_mentors(sport_id: int, session: SessionDep, _: CurrentUser) -> list[SportMentor]:
    """Наставники дисциплины по имени (M5·B28). 404 — для неизвестного вида спорта."""
    _get_or_404(session, sport_id)
    return sport_service.list_mentors(session, sport_id)


@router.get("/{sport_id}/recommendations")
def list_sport_recommendations(
    sport_id: int, session: SessionDep, _: CurrentUser
) -> list[SportRecommendation]:
    """Рекомендации дисциплины по id (M5·B28). 404 — для неизвестного вида спорта."""
    _get_or_404(session, sport_id)
    return sport_service.list_recommendations(session, sport_id)


@router.get("/{sport_id}/achievements")
def list_sport_achievements(
    sport_id: int, session: SessionDep, user: CurrentUser
) -> list[AchievementRead]:
    """Ачивки вида спорта со статусами (locked/in_progress/unlocked), в порядке создания.

    Поле has_proof говорит UI, есть ли видео-пруф (рисовать ли превью в карточке, S5.6).
    404 для неизвестного спорта; пустой список — если набор ещё не сгенерирован.
    Каталог sport общий, а ачивки скоупятся по владельцу (M0·B11): чужие не попадают.
    """
    _get_or_404(session, sport_id)
    achievements = session.exec(
        select(Achievement)
        .where(Achievement.sport_id == sport_id, Achievement.user_id == user.id)
        .order_by(Achievement.id)
    ).all()
    # Одним запросом — id ачивок, у которых есть пруф (без N+1 по карточкам).
    proof_ids: set[int] = (
        set(
            session.exec(
                select(AchievementProof.achievement_id).where(
                    AchievementProof.achievement_id.in_([a.id for a in achievements])
                )
            ).all()
        )
        if achievements
        else set()
    )
    return [AchievementRead(**a.model_dump(), has_proof=a.id in proof_ids) for a in achievements]


@router.post("/{sport_id}/achievements/generate", status_code=status.HTTP_201_CREATED)
def generate_sport_achievements(
    sport_id: int,
    session: SessionDep,
    user: CurrentUser,
    level: Annotated[AthleteLevel, Query()] = AthleteLevel.beginner,
) -> list[Achievement]:
    """LLM-генератор ачивок (S5.1): тированный набор под дисциплину и уровень атлета.

    Уровень — query-параметр, по умолчанию самый безопасный (beginner). Ошибка модели или
    невалидный ответ после ретраев → 502 (сбой апстрима), в БД при этом ничего не пишется.
    """
    sport = _get_or_404(session, sport_id)
    try:
        return achievement_service.generate_achievements(session, sport, level, user_id=user.id)
    except (LLMError, InvalidAchievementSetError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Не удалось получить валидный набор ачивок от модели: {exc}",
        ) from exc
