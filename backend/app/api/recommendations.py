"""Рекомендации (S4.4/S4.5): сгенерировать (вызов Opus), список истории и деталь по id.

POST /recommendations/generate — собирает снапшот, зовёт MODEL_RECO, парсит по схеме S4.3
и сохраняет `Recommendation` (input_snapshot_json, output_json, raw_text, model). Возвращает
запись с распарсенным планом и сырым текстом для отладки. Это действие по кнопке (S4.5).
GET  /recommendations — последние сохранённые рекомендации (свежие сверху), без вызова LLM.
GET  /recommendations/{id} — одна сохранённая рекомендация целиком (404, если такой нет).

Под сессией (CurrentUser) — приложение однопользовательское. Ошибка LLM или невалидный
ответ модели после ретраев → 502 (сбой апстрима), в БД при этом ничего не пишется.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.models.recommendation import Recommendation
from app.services import recommendation as reco_service
from app.services.llm import LLMError
from app.services.recommendation_schema import InvalidPlanError
from app.services.snapshot import DEFAULT_WINDOW_DAYS

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

SessionDep = Annotated[Session, Depends(get_session)]

# Сколько последних рекомендаций отдаёт список — трекер личный, история короткая.
_LIST_LIMIT = 20


@router.post("/generate", status_code=status.HTTP_201_CREATED)
def create_recommendation(
    session: SessionDep,
    user: CurrentUser,
    window_days: Annotated[int, Query(ge=1, le=365)] = DEFAULT_WINDOW_DAYS,
) -> Recommendation:
    try:
        return reco_service.generate_recommendation(
            session, user_id=user.id, window_days=window_days
        )
    except (LLMError, InvalidPlanError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Не удалось получить валидную рекомендацию от модели: {exc}",
        ) from exc


@router.get("")
def list_recommendations(session: SessionDep, _: CurrentUser) -> list[Recommendation]:
    return list(
        session.exec(
            select(Recommendation).order_by(Recommendation.created_at.desc()).limit(_LIST_LIMIT)
        )
    )


@router.get("/{recommendation_id}")
def get_recommendation(
    recommendation_id: int, session: SessionDep, _: CurrentUser
) -> Recommendation:
    rec = session.get(Recommendation, recommendation_id)
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Рекомендация не найдена")
    return rec
