"""exercise_target: личные числовые цели по базовым упражнениям

Таблица личных целей пользователя по упражнениям (user_id + exercise_id, уникальная пара)
с числовым target_value и единицей. Источник целевых линий на графиках силовых/кардио.

Revision ID: c8f1a2d4e631
Revises: b7e3c1a9f240
Create Date: 2026-06-27 13:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c8f1a2d4e631'
down_revision: Union[str, Sequence[str], None] = 'b7e3c1a9f240'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "exercise_target",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("target_value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name="fk_exercise_target_user_id_user"),
        sa.ForeignKeyConstraint(
            ["exercise_id"], ["exercise.id"], name="fk_exercise_target_exercise_id_exercise"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "exercise_id", name="uq_exercise_target_user_exercise"),
    )
    op.create_index(
        op.f("ix_exercise_target_user_id"), "exercise_target", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_exercise_target_exercise_id"), "exercise_target", ["exercise_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_exercise_target_exercise_id"), table_name="exercise_target")
    op.drop_index(op.f("ix_exercise_target_user_id"), table_name="exercise_target")
    op.drop_table("exercise_target")
