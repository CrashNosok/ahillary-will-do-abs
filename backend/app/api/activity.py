"""Импорт скрина активности Welltory: превью-сверка + сохранение (S1.10, S1.11).

Два шага UI-карточки «загрузка и сверка»:
- POST /import/activity/preview — vision-разбор скрина БЕЗ записи: возвращает
  распознанные поля + raw_json, чтобы UI показал их рядом с картинкой для сверки.
- POST /import/activity — сохранение дня + исходника в `data/uploads/welltory/<date>.png`
  и `activity_day`. Идемпотентно по дню. Два режима:
    • с формой `fields`+`raw_json` (S1.11) — сохраняем выверенные пользователем
      значения, vision не дёргаем (правки сохраняются как есть);
    • без них (S1.10, обратная совместимость) — разбираем скрин и сохраняем разбор.

Роуты под сессией (CurrentUser) — приложение однопользовательское. Контролируемые
ошибки: пустой/нечитаемый скрин → 422; недоступная vision-модель → 502 (без падения).
"""

import datetime as dt
import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, ValidationError
from sqlmodel import Session

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.models.activity import ActivityDay
from app.services import llm, welltory

router = APIRouter(prefix="/import", tags=["import"])

SessionDep = Annotated[Session, Depends(get_session)]


class ActivityFields(BaseModel):
    """Восемь метрик дня Welltory (1:1 с колонками ActivityDay). None = плитки нет."""

    total_kcal: int | None = None
    active_kcal: int | None = None
    steps: int | None = None
    moving_min: int | None = None
    idle_min: int | None = None
    warmup_min: int | None = None
    active_met: int | None = None
    intense_met: int | None = None


class ActivityPreview(ActivityFields):
    """Результат шага сверки: распознанные поля + дата + сырой разбор модели."""

    date: dt.date
    raw_json: dict
    saved: bool = False


class ManualActivityIn(ActivityFields):
    """Ручной ввод дня активности: восемь метрик + дата (без скрина)."""

    date: dt.date


async def _read_image(file: UploadFile) -> bytes:
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Пустой файл изображения",
        )
    return image_bytes


@router.post("/activity/preview")
async def preview_activity(
    session: SessionDep,
    _: CurrentUser,
    file: Annotated[UploadFile, File()],
    date: Annotated[dt.date | None, Form()] = None,
) -> ActivityPreview:
    image_bytes = await _read_image(file)
    try:
        vision = welltory.parse_activity_screen(image_bytes)
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
    return ActivityPreview(
        date=date or dt.date.today(),
        raw_json=vision.raw,
        **{name: getattr(vision, name) for name in welltory.FIELD_NAMES},
    )


@router.post("/activity/manual", status_code=status.HTTP_201_CREATED)
def import_activity_manual(
    payload: ManualActivityIn,
    session: SessionDep,
    user: CurrentUser,
) -> ActivityDay:
    """Ручной ввод активности (без скрина): upsert дня по `date`. Vision не дёргаем."""
    return welltory.save_activity_day_manual(
        payload.date, session, user_id=user.id, fields=payload.model_dump(exclude={"date"})
    )


@router.post("/activity", status_code=status.HTTP_201_CREATED)
async def import_activity(
    session: SessionDep,
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
    date: Annotated[dt.date | None, Form()] = None,
    fields: Annotated[str | None, Form()] = None,
    raw_json: Annotated[str | None, Form()] = None,
) -> ActivityDay:
    image_bytes = await _read_image(file)
    day = date or dt.date.today()

    # S1.11: пользователь подтвердил/поправил поля на шаге сверки — сохраняем их.
    if fields is not None:
        try:
            parsed_fields = ActivityFields.model_validate_json(fields)
            raw = json.loads(raw_json) if raw_json else {}
        except (ValidationError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Некорректные поля активности: {exc}",
            ) from exc
        return welltory.save_activity_day_values(
            image_bytes, day, session, user_id=user.id, fields=parsed_fields.model_dump(), raw=raw
        )

    # S1.10 (обратная совместимость): полей нет — разбираем скрин и сохраняем разбор.
    try:
        return welltory.save_activity_day(image_bytes, day, session, user_id=user.id)
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
