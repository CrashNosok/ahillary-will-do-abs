"""activity_day: композитный PK (user_id, date) + перепривязка FK workout_session (M0·B7)

[HIGH RISK] Изоляция дня активности по пользователю. Раньше activity_day держал один
агрегат на дату глобально (PK = date), а workout_session.activity_date ссылалась на него
одиночным FK. Теперь день принадлежит пользователю: PK становится составным (user_id, date),
а связь тренировки с днём перепривязывается композитным FK (user_id, activity_date) →
activity_day(user_id, date).

SQLite не умеет менять состав PK через ALTER, поэтому activity_day пересобираем вручную
(новая таблица → копирование с backfill → подмена). user_id существующих строк берём как
минимальный id пользователя (единственный сид-юзер). Порядок важен из-за FK:
  upgrade:   снять старый FK на workout_session → пересобрать activity_day → навесить
             композитный FK на workout_session.
  downgrade: симметрично в обратную сторону (восстановление состояния до M0·B7).

Revision ID: e2d7c9a4b815
Revises: c4d9e2f7a318
Create Date: 2026-06-25 05:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2d7c9a4b815'
down_revision: Union[str, Sequence[str], None] = 'c4d9e2f7a318'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Колонки полезной нагрузки activity_day (без ключа user_id) — общий список для копирования
# при пересборке туда и обратно, чтобы не разъезжался между upgrade/downgrade.
_PAYLOAD_COLS = (
    "date",
    "total_kcal",
    "active_kcal",
    "steps",
    "moving_min",
    "idle_min",
    "warmup_min",
    "active_met",
    "intense_met",
    "raw_json",
    "source_image_path",
    "parsed_at",
)


def _activity_day_columns() -> list[sa.Column]:
    """Колонки полезной нагрузки activity_day (как в baseline) — общие для обеих сборок."""
    return [
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("total_kcal", sa.Integer(), nullable=True),
        sa.Column("active_kcal", sa.Integer(), nullable=True),
        sa.Column("steps", sa.Integer(), nullable=True),
        sa.Column("moving_min", sa.Integer(), nullable=True),
        sa.Column("idle_min", sa.Integer(), nullable=True),
        sa.Column("warmup_min", sa.Integer(), nullable=True),
        sa.Column("active_met", sa.Integer(), nullable=True),
        sa.Column("intense_met", sa.Integer(), nullable=True),
        sa.Column("raw_json", sa.JSON(), nullable=True),
        sa.Column("source_image_path", sa.String(), nullable=True),
        sa.Column("parsed_at", sa.DateTime(), nullable=False),
    ]


def upgrade() -> None:
    """Upgrade schema."""
    cols = ", ".join(_PAYLOAD_COLS)

    # 1) Снять старый одиночный FK: он держится за PK(date), который мы меняем.
    with op.batch_alter_table("workout_session", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_workout_session_activity_date_activity_day", type_="foreignkey"
        )

    # 2) Новая activity_day с составным PK (user_id, date) + FK user_id → user.
    op.create_table(
        "activity_day_new",
        sa.Column("user_id", sa.Integer(), nullable=False),
        *_activity_day_columns(),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name="fk_activity_day_user_id_user"),
        sa.PrimaryKeyConstraint("user_id", "date"),
    )

    # 3) Перенос с backfill: владелец каждого существующего дня — минимальный id пользователя.
    op.execute(
        f"INSERT INTO activity_day_new (user_id, {cols}) "
        f"SELECT (SELECT MIN(id) FROM user), {cols} FROM activity_day"
    )

    # 4) Подмена таблицы + индекс по user_id (как index=True в модели).
    op.drop_table("activity_day")
    op.rename_table("activity_day_new", "activity_day")
    op.create_index(op.f("ix_activity_day_user_id"), "activity_day", ["user_id"], unique=False)

    # 5) Перепривязать workout_session.activity_date композитным FK на новый PK.
    with op.batch_alter_table("workout_session", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_workout_session_activity_day",
            "activity_day",
            ["user_id", "activity_date"],
            ["user_id", "date"],
        )


def downgrade() -> None:
    """Downgrade schema (возврат к глобальному дню активности с PK = date)."""
    cols = ", ".join(_PAYLOAD_COLS)

    # 1) Снять композитный FK.
    with op.batch_alter_table("workout_session", schema=None) as batch_op:
        batch_op.drop_constraint("fk_workout_session_activity_day", type_="foreignkey")

    # 2) Вернуть activity_day с PK(date) без user_id. Если бы было несколько пользователей с
    #    одной датой — здесь возможна коллизия PK(date); в однопользовательском режиме её нет.
    op.drop_index(op.f("ix_activity_day_user_id"), table_name="activity_day")
    op.create_table(
        "activity_day_old",
        *_activity_day_columns(),
        sa.PrimaryKeyConstraint("date"),
    )
    op.execute(f"INSERT INTO activity_day_old ({cols}) SELECT {cols} FROM activity_day")
    op.drop_table("activity_day")
    op.rename_table("activity_day_old", "activity_day")

    # 3) Восстановить старый одиночный FK.
    with op.batch_alter_table("workout_session", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_workout_session_activity_date_activity_day",
            "activity_day",
            ["activity_date"],
            ["date"],
        )
