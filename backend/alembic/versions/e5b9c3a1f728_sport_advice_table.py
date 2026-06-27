"""sport_advice: ИИ-рекомендация по конкретному виду спорта (последняя на user+sport)

Revision ID: e5b9c3a1f728
Revises: d4a8b6c2e915
Create Date: 2026-06-27 14:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5b9c3a1f728'
down_revision: Union[str, Sequence[str], None] = 'd4a8b6c2e915'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sport_advice",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("sport_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name="fk_sport_advice_user_id_user"),
        sa.ForeignKeyConstraint(["sport_id"], ["sport.id"], name="fk_sport_advice_sport_id_sport"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "sport_id", name="uq_sport_advice_user_sport"),
    )
    op.create_index(op.f("ix_sport_advice_user_id"), "sport_advice", ["user_id"], unique=False)
    op.create_index(op.f("ix_sport_advice_sport_id"), "sport_advice", ["sport_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_sport_advice_sport_id"), table_name="sport_advice")
    op.drop_index(op.f("ix_sport_advice_user_id"), table_name="sport_advice")
    op.drop_table("sport_advice")
