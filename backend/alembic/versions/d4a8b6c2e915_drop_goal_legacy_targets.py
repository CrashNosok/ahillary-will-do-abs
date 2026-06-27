"""smart_goal: удалить легаси-колонки целей (target_weight_kg/body_fat/measurements)

Данные уже перенесены в target_metrics_json (миграция b7e3c1a9f240). Единственный источник
правды для целей — target_metrics_json; старые типовые колонки больше не используются и
удаляются. downgrade возвращает их пустыми (nullable) для отката схемы.

Revision ID: d4a8b6c2e915
Revises: c8f1a2d4e631
Create Date: 2026-06-27 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4a8b6c2e915'
down_revision: Union[str, Sequence[str], None] = 'c8f1a2d4e631'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("smart_goal", schema=None) as batch_op:
        batch_op.drop_column("target_weight_kg")
        batch_op.drop_column("target_body_fat_pct")
        batch_op.drop_column("target_measurements_json")


def downgrade() -> None:
    with op.batch_alter_table("smart_goal", schema=None) as batch_op:
        batch_op.add_column(sa.Column("target_measurements_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("target_body_fat_pct", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("target_weight_kg", sa.Float(), nullable=True))
