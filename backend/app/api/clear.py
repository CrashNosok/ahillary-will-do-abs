"""«Очистить» данные дня/недели (удаление с архивацией).

POST /day-data/clear {category, date} — переносит данные категории за дату в архив
(deleted_record) и удаляет из живой таблицы. Категория = вкладка редактора: food/activity/
training/weight/measurements/photos. Скоуп — CurrentUser.
"""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.services.clear import clear_category

router = APIRouter(prefix="/day-data", tags=["clear"])

SessionDep = Annotated[Session, Depends(get_session)]


class ClearIn(BaseModel):
    category: str
    date: dt.date


@router.post("/clear")
def clear(body: ClearIn, session: SessionDep, user: CurrentUser) -> dict[str, int]:
    """Очищает (с архивацией) данные категории за дату. Неизвестная категория → 422."""
    try:
        cleared = clear_category(session, user.id, body.category, body.date)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return {"cleared": cleared}
