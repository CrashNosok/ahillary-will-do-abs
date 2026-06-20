"""Фундамент БД (SQLModel + SQLite): init_db создаёт файл/каталоги, dependency даёт сессию."""

from sqlalchemy import text

from app.core import config, db


def test_init_db_creates_db_file_and_data_dirs(tmp_path, monkeypatch):
    # Каталог данных и движок направляем во временную папку, чтобы не трогать backend/data.
    monkeypatch.setattr(config.settings, "data_dir", tmp_path)
    monkeypatch.setattr(db, "engine", db.make_engine(tmp_path / "app.db"))

    db.init_db()

    assert (tmp_path / "app.db").exists()  # критерий: при первом запуске создаётся app.db
    assert (tmp_path / "uploads").is_dir()
    assert (tmp_path / "videos").is_dir()


def test_init_db_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "data_dir", tmp_path)
    monkeypatch.setattr(db, "engine", db.make_engine(tmp_path / "app.db"))

    db.init_db()
    db.init_db()  # повторный старт не должен падать

    assert (tmp_path / "app.db").exists()


def test_get_session_yields_working_session(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "engine", db.make_engine(tmp_path / "app.db"))

    gen = db.get_session()
    session = next(gen)
    try:
        assert session.execute(text("SELECT 1")).scalar() == 1  # критерий: рабочая сессия
    finally:
        gen.close()
