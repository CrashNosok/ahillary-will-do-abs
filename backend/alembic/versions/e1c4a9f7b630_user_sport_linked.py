"""user_sport.linked (мягкая отвязка)

Флаг активности связки: отвязка снимает linked, но строку (с уровнем/рейтингом) сохраняет, чтобы
персональный прогресс не сбрасывался. Существующие связки = linked (server_default '1').

Revision ID: e1c4a9f7b630
Revises: c9d3a1f7b520
Create Date: 2026-06-26
"""

import sqlalchemy as sa
from alembic import op

revision = "e1c4a9f7b630"
down_revision = "c9d3a1f7b520"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_sport", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("linked", sa.Boolean(), nullable=False, server_default=sa.text("1"))
        )


def downgrade() -> None:
    with op.batch_alter_table("user_sport", schema=None) as batch_op:
        batch_op.drop_column("linked")
