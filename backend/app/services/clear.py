"""Очистка данных дня/недели с архивацией (soft-delete для кнопки «Очистить»).

clear_category переносит строки выбранной категории за дату в deleted_record (payload = JSON
строки) и удаляет их из живой таблицы. Тренировки тянут за собой свои медиа (workout_media).
Файлы медиа на диске НЕ удаляем — путь сохранён в архиве, данные восстановимы.
"""

import datetime as dt
import json

from sqlmodel import Session, select

from app.models.activity import ActivityDay
from app.models.body import BodyMeasurement, InbodyMeasurement, ProgressPhoto
from app.models.deleted import DeletedRecord
from app.models.nutrition import FoodEntry
from app.models.workout import WorkoutMedia, WorkoutSession

# Категория редактора дня/недели → модель (все по user_id + date).
_MODELS = {
    "food": FoodEntry,
    "activity": ActivityDay,
    "training": WorkoutSession,
    "weight": InbodyMeasurement,
    "measurements": BodyMeasurement,
    "photos": ProgressPhoto,
}

CATEGORIES = frozenset(_MODELS)


def _archive(session: Session, user_id: int, table: str, row) -> None:
    """Кладёт удаляемую строку в архив как JSON (default=str — для дат/datetime)."""
    session.add(
        DeletedRecord(
            user_id=user_id,
            source_table=table,
            payload=json.dumps(row.model_dump(), default=str),
        )
    )


def clear_category(session: Session, user_id: int, category: str, date: dt.date) -> int:
    """Архивирует и удаляет данные категории за дату (скоуп по user_id). Возвращает число
    удалённых строк. Неизвестная категория → ValueError."""
    model = _MODELS.get(category)
    if model is None:
        raise ValueError(f"Неизвестная категория: {category}")

    rows = session.exec(
        select(model).where(model.user_id == user_id, model.date == date)
    ).all()
    cleared = 0
    for row in rows:
        if category == "training":  # тренировка тянет свои медиа
            media = session.exec(
                select(WorkoutMedia).where(WorkoutMedia.session_id == row.id)
            ).all()
            for m in media:
                _archive(session, user_id, "workout_media", m)
                session.delete(m)
        _archive(session, user_id, model.__tablename__, row)
        session.delete(row)
        cleared += 1
    session.commit()
    return cleared
