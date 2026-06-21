"""Фундамент БД: SQLModel engine, session-фабрика и инициализация хранилища.

SQLite-файл лежит в data/app.db. Схема приводится к head через Alembic при старте
(см. init_db → _migrate_to_head). Здесь же создаются каталоги для загрузок и видео.
"""

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, inspect
from sqlmodel import Session, create_engine

import app.models  # noqa: F401 — регистрирует таблицы в SQLModel.metadata
from app.core.config import settings

# backend/ — корень бэкенда (db.py лежит в backend/app/core/).
_BACKEND_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = _BACKEND_DIR  # экспортируем для построения относительных путей к загрузкам

# Подкаталоги под локальные данные (parents=True заодно создаёт сам data/).
_SUBDIRS = ("uploads", "videos")


def _data_dir() -> Path:
    """Каталог данных. Относительный путь якорим к backend/, чтобы не зависеть от CWD."""
    data_dir = settings.data_dir
    return data_dir if data_dir.is_absolute() else _BACKEND_DIR / data_dir


def welltory_dir() -> Path:
    """Каталог исходных скринов Welltory (data/uploads/welltory). Создаётся при обращении."""
    target = _data_dir() / "uploads" / "welltory"
    target.mkdir(parents=True, exist_ok=True)
    return target


def inbody_dir() -> Path:
    """Каталог исходных скринов InBody (data/uploads/inbody). Создаётся при обращении."""
    target = _data_dir() / "uploads" / "inbody"
    target.mkdir(parents=True, exist_ok=True)
    return target


def videos_dir(achievement_id: int) -> Path:
    """Каталог видео-пруфов ачивки (data/videos/<achievement_id>). Создаётся при обращении."""
    target = _data_dir() / "videos" / str(achievement_id)
    target.mkdir(parents=True, exist_ok=True)
    return target


def make_engine(db_path: Path) -> Engine:
    """SQLite-движок. check_same_thread=False — сессии живут в разных потоках FastAPI."""
    return create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})


engine = make_engine(_data_dir() / "app.db")

# alembic.ini лежит в backend/ (рядом с app/). Конфиг строим от него.
_ALEMBIC_INI = _BACKEND_DIR / "alembic.ini"


def _migrate_to_head() -> None:
    """Приводит схему к Alembic head на текущем engine (его монкейпатчат тесты).

    Чистая БД → upgrade head создаёт всю схему. Доalembic-овская БД (таблицы есть,
    alembic_version нет) — штампуем baseline, чтобы adopt существующие данные без падения.
    """
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(_ALEMBIC_INI))
    cfg.attributes["connection"] = engine  # env.py возьмёт именно этот движок
    tables = set(inspect(engine).get_table_names())
    if "user" in tables and "alembic_version" not in tables:
        command.stamp(cfg, "head")
    else:
        command.upgrade(cfg, "head")


def init_db() -> None:
    """Создаёт каталоги данных и приводит схему к Alembic head.

    Идемпотентно — вызывается на старте приложения (повторный upgrade head — no-op).
    """
    data_dir = _data_dir()
    for sub in _SUBDIRS:
        (data_dir / sub).mkdir(parents=True, exist_ok=True)
    _migrate_to_head()


def get_session() -> Iterator[Session]:
    """FastAPI-зависимость: отдаёт сессию на время запроса и закрывает её после."""
    with Session(engine) as session:
        yield session
