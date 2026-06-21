"""Импорт скрина активности Welltory: разбор + сохранение дня (S1.10).

POST /import/activity — multipart-картинка (поле `file`) и опциональная дата дня
(поле `date`, ISO `YYYY-MM-DD`; по умолчанию сегодня). Vision-модель разбирает
скрин, исходник кладётся в `data/uploads/welltory/<date>.png`, день пишется в
`activity_day` (поля + raw_json + source_image_path + parsed_at). Идемпотентно
по дню. Роут под сессией (CurrentUser) — приложение однопользовательское.

Контролируемые ошибки: пустой файл / нечитаемый скрин → 422; недоступная
vision-модель (сеть/API) → 502 — сервер при этом не падает.
"""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlmodel import Session

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.models.activity import ActivityDay
from app.services import llm, welltory

router = APIRouter(prefix="/import", tags=["import"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.post("/activity", status_code=status.HTTP_201_CREATED)
async def import_activity(
    session: SessionDep,
    _: CurrentUser,
    file: Annotated[UploadFile, File()],
    date: Annotated[dt.date | None, Form()] = None,
) -> ActivityDay:
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Пустой файл изображения",
        )
    try:
        return welltory.save_activity_day(image_bytes, date or dt.date.today(), session)
    except welltory.VisionParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Не удалось разобрать скрин активности: {exc}",
        ) from exc
    except llm.LLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Vision-модель недоступна: {exc}",
        ) from exc
