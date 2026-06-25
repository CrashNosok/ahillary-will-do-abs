"""Стартовый сид: единственный пользователь + базовый каталог дисциплин.

Создаётся один раз (юзер — если таблица `user` пуста, спорт — если такого имени ещё
нет): повторный старт дублей не плодит.
"""

from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine
from app.core.security import hash_password
from app.models.sport import Sport, SportCategory, SportLevel
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

# Лестницы уровней базовых дисциплин (M7·B38): по сидированной дисциплине — упорядоченный
# набор ступеней (code, label). rank — позиция в лестнице (1 — низшая), берётся из порядка.
# Падел использует реальную любительскую градацию D/D+/C/C+/…; остальные — осмысленная
# прогрессия от новичка к мастеру. Ключи обязаны совпадать с именами из BASE_SPORTS.
BASE_SPORT_LEVELS: dict[str, tuple[tuple[str, str], ...]] = {
    "Падел": (
        ("D", "D"),
        ("D+", "D+"),
        ("C", "C"),
        ("C+", "C+"),
        ("B", "B"),
        ("B+", "B+"),
        ("A", "A"),
    ),
    "Зал": (
        ("novice", "Новичок"),
        ("amateur", "Любитель"),
        ("confident", "Уверенный"),
        ("advanced", "Продвинутый"),
        ("athlete", "Атлет"),
    ),
    "Кайт": (
        ("discovery", "Дискавери"),
        ("beginner", "Новичок"),
        ("intermediate", "Уверенный"),
        ("independent", "Самостоятельный райдер"),
        ("advanced", "Продвинутый"),
    ),
    "Эндуро": (
        ("novice", "Новичок"),
        ("hobby", "Хобби"),
        ("expert", "Эксперт"),
        ("pro", "Профи"),
    ),
    "Вейк": (
        ("beginner", "Новичок"),
        ("intermediate", "Уверенный"),
        ("advanced", "Продвинутый"),
        ("pro", "Профи"),
    ),
}


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


def seed_sport_levels(session: Session) -> int:
    """Сидит лестницы уровней базовых дисциплин, пропуская уже заведённые ступени.

    Возвращает число добавленных ступеней (0 при повторном старте). Идемпотентно:
    ступень добавляется, только если для этой дисциплины ещё нет уровня с таким code
    (uq_sport_level_sport_code). rank берётся из позиции в лестнице (1 — низшая) и
    детерминирован, поэтому повтор не конфликтует по uq_sport_level_sport_rank.
    Дисциплину, которой нет в каталоге, пропускаем — сид уровней не создаёт спорты.
    """
    added = 0
    for sport_name, ladder in BASE_SPORT_LEVELS.items():
        sport = session.exec(select(Sport).where(Sport.name == sport_name)).first()
        if sport is None:
            continue
        existing = set(
            session.exec(select(SportLevel.code).where(SportLevel.sport_id == sport.id)).all()
        )
        for rank, (code, label) in enumerate(ladder, start=1):
            if code in existing:
                continue
            session.add(SportLevel(sport_id=sport.id, code=code, label=label, rank=rank))
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


def seed_initial_sport_levels() -> None:
    """Точка вызова на старте: открывает сессию и сидит лестницы уровней дисциплин."""
    with Session(engine) as session:
        seed_sport_levels(session)
