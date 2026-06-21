"""Alembic env: метаданные берём из SQLModel, движок — из приложения.

target_metadata = SQLModel.metadata (после импорта app.models регистрируются все таблицы),
поэтому autogenerate видит модели. В online-режиме переиспользуем app.core.db.engine —
тот же, что монкейпатчат тесты и что использует init_db, чтобы миграции шли по нужной БД.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection, Engine
from sqlmodel import SQLModel

import app.models  # noqa: F401 — регистрирует таблицы в SQLModel.metadata
from app.core.db import engine as app_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def _configure_and_run(connection: Connection) -> None:
    # render_as_batch — SQLite не умеет полноценный ALTER, batch-режим нужен будущим миграциям.
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """Генерация SQL без подключения (alembic upgrade --sql)."""
    context.configure(
        url=str(app_engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Online-режим. Соединение передаёт init_db (через config.attributes),
    иначе (CLI `alembic …`) открываем своё на app-движке."""
    connectable = config.attributes.get("connection", None) or app_engine
    if isinstance(connectable, Connection):
        _configure_and_run(connectable)
    elif isinstance(connectable, Engine):
        with connectable.connect() as connection:
            _configure_and_run(connection)
    else:  # уже что-то соединениеподобное
        _configure_and_run(connectable)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
