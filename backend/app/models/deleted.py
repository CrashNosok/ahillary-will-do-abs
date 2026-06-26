"""Архив удалённых данных (soft-delete). «Очистить» в редакторе дня/недели не стирает данные
насовсем, а переносит каждую удалённую строку сюда: payload — её JSON, source_table — откуда.
Файлы медиа на диске не трогаем (путь сохранён в payload) — данные восстановимы по архиву."""

import datetime as dt

from sqlmodel import Field, SQLModel

from app.models._time import utcnow


class DeletedRecord(SQLModel, table=True):
    __tablename__ = "deleted_record"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    source_table: str = Field(index=True)  # таблица, из которой удалили строку
    payload: str  # JSON удалённой строки (default=str для дат)
    deleted_at: dt.datetime = Field(default_factory=utcnow)
