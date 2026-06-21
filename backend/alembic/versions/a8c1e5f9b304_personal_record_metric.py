"""personal_record: add metric discriminator (S3.10)

Карточка S3.10 «PR-движок: 1ПМ, тоннаж, авто-PR»: фиксировать рекорды разного рода
(макс вес / лучший 1ПМ / лучший темп / макс дистанция). Чтобы сравнивать новый результат
с лучшим того же РОДА, добавляем personal_record.metric — дискриминатор записи.
Baseline (S1.2) создал personal_record без него; таблица пустая (PR-движок появляется тут).

Revision ID: a8c1e5f9b304
Revises: f7a5c9d2e483
Create Date: 2026-06-21 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8c1e5f9b304'
down_revision: Union[str, Sequence[str], None] = 'f7a5c9d2e483'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('personal_record', schema=None) as batch_op:
        batch_op.add_column(sa.Column('metric', sa.String(), nullable=False))
        batch_op.create_index(
            batch_op.f('ix_personal_record_metric'), ['metric'], unique=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('personal_record', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_personal_record_metric'))
        batch_op.drop_column('metric')
