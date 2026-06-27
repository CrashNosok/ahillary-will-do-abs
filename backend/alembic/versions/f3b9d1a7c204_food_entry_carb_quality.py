"""food_entry: fiber_g, sugar_g, saturated_fat_g — детальные нутриенты для отчёта

FatSecret-CSV содержит клетчатку (Клетч, col5), сахар (Сахар, col6) и насыщенные жиры
(Н·жир, col3) — парсер теперь их читает. Колонки nullable: существующие строки остаются
NULL (бэкфилл невозможен — исходные CSV не хранятся), значения появляются при повторном
импорте дня.

Revision ID: f3b9d1a7c204
Revises: e5b9c3a1f728
Create Date: 2026-06-28 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f3b9d1a7c204'
down_revision: Union[str, Sequence[str], None] = 'e5b9c3a1f728'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("food_entry", sa.Column("fiber_g", sa.Float(), nullable=True))
    op.add_column("food_entry", sa.Column("sugar_g", sa.Float(), nullable=True))
    op.add_column("food_entry", sa.Column("saturated_fat_g", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("food_entry") as batch:
        batch.drop_column("saturated_fat_g")
        batch.drop_column("sugar_g")
        batch.drop_column("fiber_g")
