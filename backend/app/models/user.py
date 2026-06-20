"""Модель единственного пользователя приложения.

Регистрации и мультиюзера нет (S0.6) — пользователь один, создаётся сидом при старте
(см. app.core.seed). Пароль хранится только как bcrypt-хэш (см. app.core.security).
"""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class User(SQLModel, table=True):
    """Пользователь: email + bcrypt-хэш пароля. Таблица называется `user`."""

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    password_hash: str
    created_at: datetime = Field(default_factory=_utcnow)
