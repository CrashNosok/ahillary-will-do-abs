"""Фундамент БД: SQLModel engine, session-фабрика и инициализация хранилища.

SQLite-файл лежит в data/app.db. Схема создаётся через create_all при старте —
Alembic вводим в Sprint 2. Здесь же создаются каталоги для загрузок и видео.
"""

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings

# backend/ — корень бэкенда (db.py лежит в backend/app/core/).
_BACKEND_DIR = Path(__file__).resolve().parents[2]

# Подкаталоги под локальные данные (parents=True заодно создаёт сам data/).
_SUBDIRS = ("uploads", "videos")


def _data_dir() -> Path:
    """Каталог данных. Относительный путь якорим к backend/, чтобы не зависеть от CWD."""
    data_dir = settings.data_dir
    return data_dir if data_dir.is_absolute() else _BACKEND_DIR / data_dir


def make_engine(db_path: Path) -> Engine:
    """SQLite-движок. check_same_thread=False — сессии живут в разных потоках FastAPI."""
    return create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})


engine = make_engine(_data_dir() / "app.db")


def init_db() -> None:
    """Создаёт каталоги данных и таблицы. Идемпотентно — вызывается на старте приложения."""
    data_dir = _data_dir()
    for sub in _SUBDIRS:
        (data_dir / sub).mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """FastAPI-зависимость: отдаёт сессию на время запроса и закрывает её после."""
    with Session(engine) as session:
        yield session
