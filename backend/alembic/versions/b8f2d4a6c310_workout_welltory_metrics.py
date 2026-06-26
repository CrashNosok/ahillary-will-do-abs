"""workout_session: метрики Welltory «Анализ тренировки» (ядро 9671)

Revision ID: b8f2d4a6c310
Revises: a7c1e3b95d20
Create Date: 2026-06-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8f2d4a6c310'
down_revision: Union[str, Sequence[str], None] = 'a7c1e3b95d20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLS = (
    'total_kcal',
    'active_kcal',
    'total_met',
    'useful_met',
    'hr_avg',
    'hr_max',
    'load_pct',
    'score',
)


def upgrade() -> None:
    """Upgrade schema."""
    for col in _COLS:
        op.add_column('workout_session', sa.Column(col, sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('workout_session') as batch:
        for col in reversed(_COLS):
            batch.drop_column(col)
