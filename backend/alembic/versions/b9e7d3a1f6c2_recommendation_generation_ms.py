"""recommendation: add generation_ms (S4.9)

Карточка S4.9 «Обработка ошибок и стоимости»: показывать время генерации рекомендации.
Храним длительность вызова модели (мс) на самой записи рядом с именем модели. Nullable —
у записей до S4.9 значения нет, UI тогда показывает только модель.

Revision ID: b9e7d3a1f6c2
Revises: a8c1e5f9b304
Create Date: 2026-06-21 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9e7d3a1f6c2'
down_revision: Union[str, Sequence[str], None] = 'a8c1e5f9b304'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('recommendation', schema=None) as batch_op:
        batch_op.add_column(sa.Column('generation_ms', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('recommendation', schema=None) as batch_op:
        batch_op.drop_column('generation_ms')
