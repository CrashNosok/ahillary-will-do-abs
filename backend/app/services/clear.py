"""Очистка данных дня/недели с архивацией (soft-delete) и восстановление из архива.

clear_category переносит строки категории за дату в deleted_record (payload = JSON строки) и
удаляет их из живой таблицы; возвращает id созданных архивных записей (для «Отменить»).
restore_records по этим id возвращает строки обратно (с исходным id — чтобы FK медиа↔тренировка
снова сошлись) и удаляет архивные записи. Файлы медиа на диске не трогаем — путь в payload.
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

# Имя таблицы (source_table в архиве) → модель — для восстановления. Включает workout_media.
_TABLE_MODELS = {m.__tablename__: m for m in _MODELS.values()}
_TABLE_MODELS[WorkoutMedia.__tablename__] = WorkoutMedia

CATEGORIES = frozenset(_MODELS)


def _archive(session: Session, user_id: int, table: str, row) -> DeletedRecord:
    """Кладёт удаляемую строку в архив как JSON (default=str — для дат/datetime)."""
    rec = DeletedRecord(
        user_id=user_id,
        source_table=table,
        payload=json.dumps(row.model_dump(), default=str),
    )
    session.add(rec)
    return rec


def clear_category(session: Session, user_id: int, category: str, date: dt.date) -> list[int]:
    """Архивирует и удаляет данные категории за дату (скоуп по user_id). Возвращает id архивных
    записей (для «Отменить»). Неизвестная категория → ValueError."""
    model = _MODELS.get(category)
    if model is None:
        raise ValueError(f"Неизвестная категория: {category}")

    rows = session.exec(
        select(model).where(model.user_id == user_id, model.date == date)
    ).all()
    archived: list[DeletedRecord] = []
    for row in rows:
        if category == "training":  # тренировка тянет свои медиа
            media = session.exec(
                select(WorkoutMedia).where(WorkoutMedia.session_id == row.id)
            ).all()
            for m in media:
                archived.append(_archive(session, user_id, "workout_media", m))
                session.delete(m)
        archived.append(_archive(session, user_id, model.__tablename__, row))
        session.delete(row)
    session.commit()
    return [a.id for a in archived]


def restore_records(session: Session, user_id: int, ids: list[int]) -> int:
    """Возвращает архивные записи (по id, скоуп user_id) обратно в их таблицы и удаляет из архива.
    Тренировку восстанавливаем раньше её медиа (FK). Возвращает число восстановленных строк."""
    recs = session.exec(
        select(DeletedRecord).where(
            DeletedRecord.user_id == user_id, DeletedRecord.id.in_(ids)
        )
    ).all()
    recs.sort(key=lambda r: r.source_table == "workout_media")  # медиа — последними
    restored = 0
    for rec in recs:
        model = _TABLE_MODELS.get(rec.source_table)
        if model is None:
            continue
        # model_validate (а не model(**...)): table-модели SQLModel не валидируют в __init__,
        # и ISO-строки дат остались бы строками → SQLite DateTime их отвергает. Здесь — коэрсим.
        session.add(model.model_validate(json.loads(rec.payload)))
        session.delete(rec)
        restored += 1
    session.commit()
    return restored
