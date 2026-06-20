"""Сид единственного пользователя: создаётся один раз с хэшем, повторный старт не плодит дубли."""

from sqlmodel import Session, select

from app.core import config, db
from app.core.security import verify_password
from app.core.seed import seed_user
from app.models.user import User


def _prepare_db(tmp_path, monkeypatch, email="seed@example.com", password="s3cret-pw"):
    # Движок и сид-креды направляем во временную папку/значения, чтобы не трогать backend/data.
    monkeypatch.setattr(config.settings, "data_dir", tmp_path)
    monkeypatch.setattr(db, "engine", db.make_engine(tmp_path / "app.db"))
    monkeypatch.setattr(config.settings, "seed_user_email", email)
    monkeypatch.setattr(config.settings, "seed_user_password", password)
    db.init_db()


def test_seed_creates_single_hashed_user(tmp_path, monkeypatch):
    _prepare_db(tmp_path, monkeypatch)

    with Session(db.engine) as session:
        created = seed_user(session)

    assert created is not None  # критерий: сид-юзер создаётся
    assert created.email == "seed@example.com"
    assert created.password_hash != "s3cret-pw"  # критерий: пароль захэширован
    assert verify_password("s3cret-pw", created.password_hash)

    with Session(db.engine) as session:
        users = session.exec(select(User)).all()
    assert len(users) == 1


def test_seed_is_idempotent_no_duplicates(tmp_path, monkeypatch):
    _prepare_db(tmp_path, monkeypatch)

    with Session(db.engine) as session:
        seed_user(session)
    with Session(db.engine) as session:
        again = seed_user(session)  # повторный старт

    assert again is None  # таблица не пуста — нового юзера не создаём
    with Session(db.engine) as session:
        users = session.exec(select(User)).all()
    assert len(users) == 1  # критерий: дублей нет
