"""food_entry: created_at — для порядка заливки дня

Чтобы знать порядок появления категорий за день (еда/активность/тренировка), еде нужна
временная метка (у тренировки created_at и у активности parsed_at уже есть). Существующим
строкам проставляем created_at = date (полночь дня) — истинный порядок старых дней не
восстановить, новые записи будут с реальным временем.

Revision ID: f4a9c2d7e810
Revises: d5e9a3c1f042
Create Date: 2026-06-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4a9c2d7e810'
down_revision: Union[str, Sequence[str], None] = 'd5e9a3c1f042'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('food_entry', sa.Column('created_at', sa.DateTime(), nullable=True))
    # backfill: время = начало дня записи (детерминированно; старые дни — приблизительный порядок)
    op.execute("UPDATE food_entry SET created_at = date WHERE created_at IS NULL")


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('food_entry') as batch:
        batch.drop_column('created_at')
