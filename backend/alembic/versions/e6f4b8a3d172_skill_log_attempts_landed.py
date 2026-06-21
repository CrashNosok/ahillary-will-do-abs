"""skill_log: add attempts + landed (S3.6)

Карточка S3.6 задаёт skill_log(exercise_id, attempts, landed, notes) — прогресс по
элементам (вейкборд/BMX/эндуро): сколько попыток и сколько удачных приземлений.
Baseline (S1.2) создал skill_log без attempts/landed. Здесь добавляем их под критерий
«видно прогресс по элементам (landed/попытки)». Остальные поля baseline не трогаем.

Revision ID: e6f4b8a3d172
Revises: d5e3a9b2c641
Create Date: 2026-06-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6f4b8a3d172'
down_revision: Union[str, Sequence[str], None] = 'd5e3a9b2c641'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('skill_log', schema=None) as batch_op:
        batch_op.add_column(sa.Column('attempts', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('landed', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('skill_log', schema=None) as batch_op:
        batch_op.drop_column('landed')
        batch_op.drop_column('attempts')
