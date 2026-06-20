"""Стартовый сид: единственный пользователь из SEED_USER_EMAIL/PASSWORD.

Создаётся один раз, если таблица `user` пуста — повторный старт дублей не плодит.
"""

from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine
from app.core.security import hash_password
from app.models.user import User


def seed_user(session: Session) -> User | None:
    """Создаёт сид-юзера, если таблица пуста. Возвращает нового User либо None (уже есть)."""
    if session.exec(select(User)).first() is not None:
        return None
    user = User(
        email=settings.seed_user_email,
        password_hash=hash_password(settings.seed_user_password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def seed_initial_user() -> None:
    """Точка вызова на старте: открывает сессию и сидит пользователя при необходимости."""
    with Session(engine) as session:
        seed_user(session)
