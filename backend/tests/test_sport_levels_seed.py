"""Сид лестниц уровней дисциплин (M7·B38): ступени для сидированных спортов, идемпотентно."""

from sqlmodel import Session, select

from app.core import db
from app.core.seed import BASE_SPORT_LEVELS, BASE_SPORTS, seed_sport_levels, seed_sports
from app.models.sport import Sport, SportLevel


def _prepare_db(tmp_path, monkeypatch):
    # Движок направляем во временную папку, чтобы не трогать backend/data.
    monkeypatch.setattr(db, "engine", db.make_engine(tmp_path / "app.db"))
    db.init_db()


def test_level_ladders_only_for_seeded_sports():
    # Защита от рассинхрона: каждая лестница должна ссылаться на реально сидируемую дисциплину.
    seeded_names = {name for name, _ in BASE_SPORTS}
    assert set(BASE_SPORT_LEVELS) <= seeded_names


def test_seed_creates_ladders_for_seeded_sports(tmp_path, monkeypatch):
    _prepare_db(tmp_path, monkeypatch)
    with Session(db.engine) as session:
        seed_sports(session)
        added = seed_sport_levels(session)

    total = sum(len(ladder) for ladder in BASE_SPORT_LEVELS.values())
    assert added == total  # все ступени всех лестниц добавлены

    with Session(db.engine) as session:
        padel = session.exec(select(Sport).where(Sport.name == "Падел")).one()
        levels = session.exec(
            select(SportLevel).where(SportLevel.sport_id == padel.id).order_by(SportLevel.rank)
        ).all()

    # критерий карточки: падел D/D+/C/C+ и т.п. в порядке rank, ранги 1..N подряд
    assert [lvl.code for lvl in levels] == ["D", "D+", "C", "C+", "B", "B+", "A"]
    assert [lvl.rank for lvl in levels] == [1, 2, 3, 4, 5, 6, 7]


def test_every_seeded_sport_gets_a_ladder(tmp_path, monkeypatch):
    _prepare_db(tmp_path, monkeypatch)
    with Session(db.engine) as session:
        seed_sports(session)
        seed_sport_levels(session)

    with Session(db.engine) as session:
        for sport_name, ladder in BASE_SPORT_LEVELS.items():
            sport = session.exec(select(Sport).where(Sport.name == sport_name)).one()
            codes = session.exec(
                select(SportLevel.code)
                .where(SportLevel.sport_id == sport.id)
                .order_by(SportLevel.rank)
            ).all()
            assert list(codes) == [code for code, _ in ladder]


def test_seed_levels_is_idempotent_no_duplicates(tmp_path, monkeypatch):
    _prepare_db(tmp_path, monkeypatch)
    with Session(db.engine) as session:
        seed_sports(session)
        seed_sport_levels(session)
    with Session(db.engine) as session:
        added_again = seed_sport_levels(session)  # повторный старт

    assert added_again == 0  # повтор ничего не добавляет

    with Session(db.engine) as session:
        rows = session.exec(select(SportLevel.sport_id, SportLevel.code)).all()
    assert len(rows) == len(set(rows))  # дублей (sport_id, code) нет


def test_seed_levels_fills_only_missing_steps(tmp_path, monkeypatch):
    # Часть лестницы заведена вручную — сид добавляет лишь недостающие ступени, без коллизий rank.
    _prepare_db(tmp_path, monkeypatch)
    with Session(db.engine) as session:
        seed_sports(session)
        padel = session.exec(select(Sport).where(Sport.name == "Падел")).one()
        session.add(SportLevel(sport_id=padel.id, code="D", label="D", rank=1))
        session.commit()

    with Session(db.engine) as session:
        added = seed_sport_levels(session)

    padel_steps = len(BASE_SPORT_LEVELS["Падел"])
    other_steps = sum(len(v) for k, v in BASE_SPORT_LEVELS.items() if k != "Падел")
    # «D» у падела уже была — добавились остальные ступени падела + все ступени прочих дисциплин
    assert added == (padel_steps - 1) + other_steps

    with Session(db.engine) as session:
        padel = session.exec(select(Sport).where(Sport.name == "Падел")).one()
        codes = session.exec(
            select(SportLevel.code).where(SportLevel.sport_id == padel.id).order_by(SportLevel.rank)
        ).all()
    assert list(codes) == ["D", "D+", "C", "C+", "B", "B+", "A"]


def test_seed_levels_skips_unknown_sports(tmp_path, monkeypatch):
    # Каталог пуст (спорты не сидированы) — уровням не на что опереться, сид ничего не пишет.
    _prepare_db(tmp_path, monkeypatch)
    with Session(db.engine) as session:
        added = seed_sport_levels(session)

    assert added == 0
    with Session(db.engine) as session:
        assert session.exec(select(SportLevel)).all() == []
