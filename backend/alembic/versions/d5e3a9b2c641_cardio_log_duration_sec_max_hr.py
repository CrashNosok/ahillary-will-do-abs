"""cardio_log: duration_sec + max_hr (S3.5)

Карточка S3.5 задаёт cardio_log(distance_km, duration_sec, avg_hr, max_hr).
Baseline (S1.2) создал cardio_log с duration_min и без max_hr. Здесь приводим к карточке:
duration_min → duration_sec (кардио ещё не логировалось — данных для конвертации нет)
и добавляем пиковый пульс max_hr. Темп (avg_pace) считается в API из дистанции/времени.

Revision ID: d5e3a9b2c641
Revises: b4d2f8c1a907
Create Date: 2026-06-21 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5e3a9b2c641'
down_revision: Union[str, Sequence[str], None] = 'b4d2f8c1a907'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('cardio_log', schema=None) as batch_op:
        batch_op.alter_column('duration_min', new_column_name='duration_sec')
        batch_op.add_column(sa.Column('max_hr', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('cardio_log', schema=None) as batch_op:
        batch_op.drop_column('max_hr')
        batch_op.alter_column('duration_sec', new_column_name='duration_min')
