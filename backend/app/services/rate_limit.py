"""Кулдаун на платные LLM-генерации: «не чаще раза в N минут», меряем по created_at
последней записи в БД (отдельного хранилища попыток нет).

ponytail: лимит по времени последней строки — без Redis/счётчиков. Несколько воркеров
видят одну БД, поэтому ограничение честное. Минус — нельзя «простить» одну попытку,
но для платного эндпоинта потолка «раз в N минут» достаточно. Per-user стораджа добавим,
если понадобится сбрасывать лимит вручную.
"""

import datetime as dt

from fastapi import HTTPException, status

from app.models._time import utcnow


def enforce_cooldown(last_created_at: dt.datetime | None, cooldown: dt.timedelta) -> None:
    """Поднять 429 (+Retry-After), если с last_created_at прошло меньше cooldown.

    last_created_at из SQLite может прийти наивным (без tz) — трактуем как UTC, иначе
    вычитание aware−naive падает. None (записи ещё нет) — всегда разрешаем.
    """
    if last_created_at is None:
        return
    if last_created_at.tzinfo is None:
        last_created_at = last_created_at.replace(tzinfo=dt.UTC)
    remaining = cooldown - (utcnow() - last_created_at)
    if remaining > dt.timedelta(0):
        secs = int(remaining.total_seconds()) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Слишком часто. Следующая генерация через ~{secs} с.",
            headers={"Retry-After": str(secs)},
        )
