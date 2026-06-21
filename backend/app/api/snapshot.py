"""LLM-снапшот (S4.1): один объект со всеми сигналами трекера для входа модели.

GET /snapshot[?window_days=N] — собирает агрегированный снапшот (см.
`app.services.snapshot`): SMART-цель и прогресс к ней, тренды питания/макросов,
активность и дефицит, замеры тела, InBody, тренировки (силовые/кардио) и текущие
персональные рекорды. window_days — длина окна сводок (1..365, по умолчанию 90).
Под сессией (CurrentUser) — приложение однопользовательское. Устойчив к пустым
данным: секции без данных отдают null / пустой список.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.services import snapshot as snapshot_service

router = APIRouter(prefix="/snapshot", tags=["snapshot"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("")
def get_snapshot(
    session: SessionDep,
    _: CurrentUser,
    window_days: Annotated[int, Query(ge=1, le=365)] = snapshot_service.DEFAULT_WINDOW_DAYS,
) -> dict[str, Any]:
    return snapshot_service.build_snapshot(session, window_days=window_days)
