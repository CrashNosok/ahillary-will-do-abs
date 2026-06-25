"""Ингест скрина InBody: превью-сверка + сохранение (S2.11).

Два шага UI-карточки «загрузка и сверка» поверх vision-парсера (services/inbody.py):
- POST /import/inbody/preview — vision-разбор скрина БЕЗ записи: возвращает пять
  ключевых полей + metrics_json, чтобы UI показал их рядом с картинкой для сверки.
- POST /import/inbody — сохранение замера + исходника в `data/uploads/inbody/<date>.png`
  и `inbody_measurement`. Идемпотентно по дню. Два режима:
    • с формой `fields`+`metrics_json` — сохраняем выверенные пользователем значения,
      vision не дёргаем (правки сохраняются как есть);
    • без них — разбираем скрин и сохраняем разбор (прямой путь для curl/smoke).

Роуты под сессией (CurrentUser) — приложение однопользовательское. Контролируемые
ошибки: пустой/нечитаемый скрин → 422; недоступная vision-модель → 502 (без падения).
"""

import datetime as dt
import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlmodel import Session

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.models.body import InbodyMeasurement
from app.services import inbody, llm

router = APIRouter(prefix="/import", tags=["import"])

SessionDep = Annotated[Session, Depends(get_session)]


class InbodyFields(BaseModel):
    """Пять ключевых показателей InBody (1:1 с промо-колонками InbodyMeasurement).

    None = поля нет на скрине / не распозналось.
    """

    weight_kg: float | None = None
    body_fat_pct: float | None = None
    muscle_mass_kg: float | None = None
    visceral_fat: float | None = None
    water: float | None = None


class InbodyPreview(InbodyFields):
    """Результат шага сверки: пять ключевых полей + дата + прочие показатели."""

    date: dt.date
    metrics_json: dict[str, Any]
    saved: bool = False


async def _read_image(file: UploadFile) -> bytes:
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Пустой файл изображения",
        )
    return image_bytes


@router.post("/inbody/preview")
async def preview_inbody(
    session: SessionDep,
    _: CurrentUser,
    file: Annotated[UploadFile, File()],
    date: Annotated[dt.date | None, Form()] = None,
) -> InbodyPreview:
    image_bytes = await _read_image(file)
    try:
        vision = inbody.parse_inbody_screen(image_bytes)
    except inbody.InbodyParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Не удалось разобрать скрин InBody: {exc}",
        ) from exc
    except llm.LLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Vision-модель недоступна: {exc}",
        ) from exc
    return InbodyPreview(
        date=date or dt.date.today(),
        metrics_json=vision.metrics_json,
        **{name: getattr(vision, name) for name in inbody.KEY_FIELD_NAMES},
    )


@router.post("/inbody", status_code=status.HTTP_201_CREATED)
async def import_inbody(
    session: SessionDep,
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
    date: Annotated[dt.date | None, Form()] = None,
    fields: Annotated[str | None, Form()] = None,
    metrics_json: Annotated[str | None, Form()] = None,
) -> InbodyMeasurement:
    image_bytes = await _read_image(file)
    day = date or dt.date.today()

    # Пользователь подтвердил/поправил поля на шаге сверки — сохраняем их.
    if fields is not None:
        try:
            parsed_fields = InbodyFields.model_validate_json(fields)
            metrics = json.loads(metrics_json) if metrics_json else {}
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Некорректные поля InBody: {exc}",
            ) from exc
        if not isinstance(metrics, dict):
            metrics = {}
        return inbody.save_inbody_values(
            image_bytes,
            day,
            session,
            user_id=user.id,
            fields=parsed_fields.model_dump(),
            metrics_json=metrics,
        )

    # Полей нет — разбираем скрин и сохраняем разбор (прямой путь для curl/smoke).
    try:
        return inbody.save_inbody_measurement(image_bytes, day, session, user_id=user.id)
    except inbody.InbodyParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Не удалось разобрать скрин InBody: {exc}",
        ) from exc
    except llm.LLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Vision-модель недоступна: {exc}",
        ) from exc
