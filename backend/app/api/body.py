"""CRUD замеров тела (S2.2): ручной ввод обхватов раз в ~2 недели.

Все обхваты в см, дата — ISO (`YYYY-MM-DD`). Полный CRUD над body_measurement:
создать/прочитать/обновить/удалить. Чтение «по дате» — фильтр `?date=` на списке;
список без фильтра отдаётся в хронологии (по возрастанию даты). Роуты под сессией
(CurrentUser) — приложение однопользовательское.
"""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.models.body import BodyMeasurement

router = APIRouter(prefix="/body-measurements", tags=["body"])

SessionDep = Annotated[Session, Depends(get_session)]


class BodyMeasurementCreate(BaseModel):
    date: dt.date
    height_cm: float | None = None
    waist_cm: float | None = None
    belly_cm: float | None = None
    calf_l_cm: float | None = None
    calf_r_cm: float | None = None
    chest_cm: float | None = None
    shoulders_cm: float | None = None
    biceps_l_cm: float | None = None
    biceps_r_cm: float | None = None
    glutes_cm: float | None = None
    notes: str | None = None


class BodyMeasurementUpdate(BaseModel):
    date: dt.date | None = None
    height_cm: float | None = None
    waist_cm: float | None = None
    belly_cm: float | None = None
    calf_l_cm: float | None = None
    calf_r_cm: float | None = None
    chest_cm: float | None = None
    shoulders_cm: float | None = None
    biceps_l_cm: float | None = None
    biceps_r_cm: float | None = None
    glutes_cm: float | None = None
    notes: str | None = None


def _get_or_404(session: Session, measurement_id: int, user_id: int) -> BodyMeasurement:
    """Замер по id, но только свой (M0·B9): чужой → 404, чтобы не раскрывать его существование."""
    measurement = session.get(BodyMeasurement, measurement_id)
    if measurement is None or measurement.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Замер не найден")
    return measurement


@router.post("", status_code=status.HTTP_201_CREATED)
def create_measurement(
    payload: BodyMeasurementCreate, session: SessionDep, user: CurrentUser
) -> BodyMeasurement:
    measurement = BodyMeasurement(**payload.model_dump(), user_id=user.id)
    session.add(measurement)
    session.commit()
    session.refresh(measurement)
    return measurement


@router.get("")
def list_measurements(
    session: SessionDep, user: CurrentUser, date: dt.date | None = None
) -> list[BodyMeasurement]:
    stmt = (
        select(BodyMeasurement)
        .where(BodyMeasurement.user_id == user.id)
        .order_by(BodyMeasurement.date, BodyMeasurement.id)
    )
    if date is not None:
        stmt = stmt.where(BodyMeasurement.date == date)
    return session.exec(stmt).all()


@router.get("/{measurement_id}")
def get_measurement(measurement_id: int, session: SessionDep, user: CurrentUser) -> BodyMeasurement:
    return _get_or_404(session, measurement_id, user.id)


@router.patch("/{measurement_id}")
def update_measurement(
    measurement_id: int,
    payload: BodyMeasurementUpdate,
    session: SessionDep,
    user: CurrentUser,
) -> BodyMeasurement:
    measurement = _get_or_404(session, measurement_id, user.id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(measurement, key, value)
    session.add(measurement)
    session.commit()
    session.refresh(measurement)
    return measurement


@router.delete("/{measurement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_measurement(measurement_id: int, session: SessionDep, user: CurrentUser) -> None:
    measurement = _get_or_404(session, measurement_id, user.id)
    session.delete(measurement)
    session.commit()
