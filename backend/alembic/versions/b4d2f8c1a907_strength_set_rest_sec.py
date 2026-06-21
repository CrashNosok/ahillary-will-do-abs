"""strength_set: add rest_sec (S3.4)

Карточка S3.4 задаёт strength_set(set_index, weight_kg, reps, rest_sec, rpe).
Baseline создал strength_set без rest_sec (S1.2). Здесь добавляем отдых между
подходами rest_sec под критерий «RPE и отдых пишутся».

Revision ID: b4d2f8c1a907
Revises: a3f1c9e7d215
Create Date: 2026-06-21 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4d2f8c1a907'
down_revision: Union[str, Sequence[str], None] = 'a3f1c9e7d215'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('strength_set', schema=None) as batch_op:
        batch_op.add_column(sa.Column('rest_sec', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('strength_set', schema=None) as batch_op:
        batch_op.drop_column('rest_sec')
