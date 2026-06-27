"""deficit_day: композитный PK (user_id, date) — изоляция дня дефицита по пользователю

[HIGH RISK] Раньше deficit_day держал PK только по date → один расчёт дефицита на дату
ГЛОБАЛЬНО. recompute одного аккаунта брал/перетирал строку другого за ту же дату
(межаккаунтная коллизия, тот же класс, что чинили для activity_day в M0·B7). Делаем PK
составным (user_id, date) — один расчёт на день у каждого пользователя.

SQLite не умеет менять состав PK через ALTER, поэтому deficit_day пересобираем вручную
(новая таблица → копирование → подмена). На deficit_day никто не ссылается FK (лист), так
что плясок с внешними ключами нет. user_id у существующих строк уже заполнен (NOT NULL +
recompute всегда его проставляет); COALESCE к MIN(user) — страховка от легаси-NULL.

Revision ID: a9e2f7c3d418
Revises: e1c4a9f7b630
Create Date: 2026-06-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9e2f7c3d418'
down_revision: Union[str, Sequence[str], None] = 'e1c4a9f7b630'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Колонки полезной нагрузки deficit_day (без ключа user_id) — общий список для копирования
# при пересборке туда и обратно, чтобы не разъезжался между upgrade/downgrade.
_PAYLOAD_COLS = (
    "date",
    "eaten_kcal",
    "burn_kcal",
    "deficit_kcal",
    "computed_at",
)


def _deficit_day_columns() -> list[sa.Column]:
    """Колонки полезной нагрузки deficit_day (как в baseline) — общие для обеих сборок."""
    return [
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("eaten_kcal", sa.Integer(), nullable=True),
        sa.Column("burn_kcal", sa.Integer(), nullable=True),
        sa.Column("deficit_kcal", sa.Integer(), nullable=True),
        sa.Column("computed_at", sa.DateTime(), nullable=False),
    ]


def upgrade() -> None:
    """Upgrade schema: PK date → составной (user_id, date)."""
    cols = ", ".join(_PAYLOAD_COLS)

    # 1) Новая deficit_day с составным PK (user_id, date) + FK user_id → user.
    op.create_table(
        "deficit_day_new",
        sa.Column("user_id", sa.Integer(), nullable=False),
        *_deficit_day_columns(),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name="fk_deficit_day_user_id_user"),
        sa.PrimaryKeyConstraint("user_id", "date"),
    )

    # 2) Перенос: user_id уже есть в строках; COALESCE к MIN(user) — страховка от легаси-NULL.
    op.execute(
        f"INSERT INTO deficit_day_new (user_id, {cols}) "
        f"SELECT COALESCE(user_id, (SELECT MIN(id) FROM user)), {cols} FROM deficit_day"
    )

    # 3) Подмена таблицы + индекс по user_id (как index=True в модели).
    op.drop_table("deficit_day")
    op.rename_table("deficit_day_new", "deficit_day")
    op.create_index(op.f("ix_deficit_day_user_id"), "deficit_day", ["user_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema (возврат к глобальному дню дефицита с PK = date).

    Если бы было несколько пользователей с одной датой — здесь возможна коллизия PK(date);
    в однопользовательском режиме её нет.
    """
    cols = ", ".join(_PAYLOAD_COLS)

    op.drop_index(op.f("ix_deficit_day_user_id"), table_name="deficit_day")
    op.create_table(
        "deficit_day_old",
        *_deficit_day_columns(),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name="fk_deficit_day_user_id_user"),
        sa.PrimaryKeyConstraint("date"),
    )
    op.execute(f"INSERT INTO deficit_day_old (user_id, {cols}) SELECT user_id, {cols} FROM deficit_day")
    op.drop_table("deficit_day")
    op.rename_table("deficit_day_old", "deficit_day")
    op.create_index(op.f("ix_deficit_day_user_id"), "deficit_day", ["user_id"], unique=False)
