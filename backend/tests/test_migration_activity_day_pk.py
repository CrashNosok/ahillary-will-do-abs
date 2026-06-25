"""Round-trip миграции M0·B7: activity_day → составной PK (user_id, date).

Критерий карточки «Тест upgrade↔downgrade»: пересборка таблицы с составным PK, backfill
владельца и перепривязка FK workout_session.activity_date должны переживать upgrade→downgrade
→upgrade без потери данных и связей. Гоняем реальную миграцию командой Alembic на временной
SQLite-БД (привязываем движок через config.attributes["connection"], как init_db).
"""

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlmodel import create_engine

import app.models  # noqa: F401 — регистрирует таблицы в SQLModel.metadata
from alembic import command

# Ревизия непосредственно перед M0·B7 (achievement user_id FK).
PRIOR = "c4d9e2f7a318"
_ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
DAY = "2026-06-20"


def _cfg(engine) -> Config:
    cfg = Config(str(_ALEMBIC_INI))
    cfg.attributes["connection"] = engine  # env.py возьмёт этот движок вместо app.db
    return cfg


@pytest.fixture
def engine(tmp_path):
    return create_engine(
        f"sqlite:///{tmp_path / 'roundtrip.db'}",
        connect_args={"check_same_thread": False},
    )


def _seed_pre_b7(engine) -> None:
    """Один пользователь + день активности (старый PK=date) + тренировка, связанная с днём."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO user (id, email, password_hash, created_at, is_active) "
                "VALUES (1, 'a@b.c', 'h', '2026-06-01 00:00:00', 1)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO activity_day (date, total_kcal, parsed_at) "
                f"VALUES ('{DAY}', 500, '2026-06-20 12:00:00')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO workout_session (id, user_id, date, activity_date, created_at) "
                f"VALUES (10, 1, '{DAY}', '{DAY}', '2026-06-20 12:00:00')"
            )
        )


def test_upgrade_builds_composite_pk_backfills_and_relinks_fk(engine):
    cfg = _cfg(engine)
    command.upgrade(cfg, PRIOR)  # схема до B7: activity_day PK(date), одиночный FK
    _seed_pre_b7(engine)

    command.upgrade(cfg, "head")  # применяем M0·B7

    insp = inspect(engine)
    assert set(insp.get_pk_constraint("activity_day")["constrained_columns"]) == {
        "user_id",
        "date",
    }
    # backfill: владелец существующего дня = минимальный id пользователя; данные целы.
    with engine.begin() as conn:
        user_id, total = conn.execute(
            text(f"SELECT user_id, total_kcal FROM activity_day WHERE date='{DAY}'")
        ).one()
    assert user_id == 1
    assert total == 500

    # FK workout_session.activity_date перепривязан композитным на (user_id, date).
    composite = [
        fk
        for fk in insp.get_foreign_keys("workout_session")
        if fk["referred_table"] == "activity_day"
    ]
    assert len(composite) == 1
    assert set(composite[0]["constrained_columns"]) == {"user_id", "activity_date"}
    assert set(composite[0]["referred_columns"]) == {"user_id", "date"}
    # связь тренировки с днём пережила пересборку.
    with engine.begin() as conn:
        linked = conn.execute(
            text("SELECT activity_date FROM workout_session WHERE id=10")
        ).scalar()
    assert str(linked) == DAY


def test_downgrade_then_upgrade_restores_state(engine):
    cfg = _cfg(engine)
    command.upgrade(cfg, PRIOR)
    _seed_pre_b7(engine)
    command.upgrade(cfg, "head")

    command.downgrade(cfg, PRIOR)  # откат M0·B7
    insp = inspect(engine)
    assert set(insp.get_pk_constraint("activity_day")["constrained_columns"]) == {"date"}
    assert "user_id" not in {c["name"] for c in insp.get_columns("activity_day")}
    # одиночный FK восстановлен, данные дня целы.
    single = [
        fk
        for fk in insp.get_foreign_keys("workout_session")
        if fk["referred_table"] == "activity_day"
    ]
    assert len(single) == 1
    assert set(single[0]["constrained_columns"]) == {"activity_date"}
    with engine.begin() as conn:
        total = conn.execute(
            text(f"SELECT total_kcal FROM activity_day WHERE date='{DAY}'")
        ).scalar()
    assert total == 500

    command.upgrade(cfg, "head")  # повторный upgrade — round-trip идемпотентен
    assert set(inspect(engine).get_pk_constraint("activity_day")["constrained_columns"]) == {
        "user_id",
        "date",
    }
