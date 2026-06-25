"""Стартовый сид: единственный пользователь + базовый каталог дисциплин.

Создаётся один раз (юзер — если таблица `user` пуста, спорт — если такого имени ещё
нет): повторный старт дублей не плодит.
"""

from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine
from app.core.security import hash_password
from app.models.sport import Sport, SportCategory
from app.models.user import User

# Базовый каталог дисциплин (M7·B37): встроенные виды спорта приложения.
# Идемпотентность держится на уникальном Sport.name — повтор пропускает уже заведённые.
BASE_SPORTS: tuple[tuple[str, SportCategory], ...] = (
    ("Зал", SportCategory.strength),
    ("Кайт", SportCategory.action),
    ("Эндуро", SportCategory.action),
    ("Вейк", SportCategory.action),
    ("Падел", SportCategory.racket),
)


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


def seed_sports(session: Session) -> int:
    """Сидит базовый каталог дисциплин, пропуская уже существующие по имени.

    Возвращает число добавленных строк (0 при повторном старте). Идемпотентно:
    уникальный Sport.name гарантирует, что повтор не плодит дубли. is_global=True —
    это встроенные дисциплины приложения, а не заведённые пользователем.
    """
    added = 0
    for name, category in BASE_SPORTS:
        if session.exec(select(Sport).where(Sport.name == name)).first() is not None:
            continue
        session.add(Sport(name=name, category=category, is_global=True))
        added += 1
    if added:
        session.commit()
    return added


def seed_initial_user() -> None:
    """Точка вызова на старте: открывает сессию и сидит пользователя при необходимости."""
    with Session(engine) as session:
        seed_user(session)


def seed_initial_sports() -> None:
    """Точка вызова на старте: открывает сессию и сидит базовый каталог дисциплин."""
    with Session(engine) as session:
        seed_sports(session)
