"""Ручной ввод веса без фото (вкладка «Ввод данных → Вес»).

Карточка просит лёгкий ввод веса раз в 1–2 недели, без скрина InBody. Вес живёт в
inbody_measurement.weight_kg (оттуда же его читает GET /progress/body), поэтому ручной
вес апсёртим в ту же строку по дню — отдельную таблицу не заводим. Если за день уже есть
InBody-замер, перетираем ТОЛЬКО weight_kg, остальные поля не трогаем.

# ponytail: переиспользуем inbody_measurement вместо новой таблицы веса — отдельную
# WeightEntry заведём, если вес понадобится вести независимо от InBody.

Роут под сессией (CurrentUser) — приложение однопользовательское.
"""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.models.body import InbodyMeasurement

router = APIRouter(prefix="/body", tags=["body"])

SessionDep = Annotated[Session, Depends(get_session)]


class WeightCreate(BaseModel):
    date: dt.date
    weight_kg: float = Field(gt=0, le=500)  # кг; границы отсекают опечатки (0, отрицательное, 3-значное)


@router.post("/weight", status_code=status.HTTP_201_CREATED)
def create_weight(payload: WeightCreate, session: SessionDep, _: CurrentUser) -> InbodyMeasurement:
    """Апсёрт веса за день в inbody_measurement (трогаем только weight_kg)."""
    existing = session.exec(
        select(InbodyMeasurement).where(InbodyMeasurement.date == payload.date)
    ).first()
    measurement = existing or InbodyMeasurement(date=payload.date)
    measurement.weight_kg = payload.weight_kg
    session.add(measurement)
    session.commit()
    session.refresh(measurement)
    return measurement
