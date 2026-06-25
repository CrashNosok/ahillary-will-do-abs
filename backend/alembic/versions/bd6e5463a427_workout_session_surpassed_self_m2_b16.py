"""workout_session surpassed_self (M2·B16)

Карточка M2·B16 добавляет в сессию тренировки флаг surpassed_self («превзошёл себя»):
bool, дефолт False. SQLite не умеет ALTER ADD COLUMN с ограничениями напрямую — идём
через op.batch_alter_table. Колонка NOT NULL, поэтому добавляем с server_default (false),
чтобы существующие строки сессий получили значение.

Revision ID: bd6e5463a427
Revises: f9a2c7b51d84
Create Date: 2026-06-25 07:38:41.662387

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # SQLModel-типы (AutoString и пр.) в autogenerate-миграциях


# revision identifiers, used by Alembic.
revision: str = 'bd6e5463a427'
down_revision: Union[str, Sequence[str], None] = 'f9a2c7b51d84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('workout_session', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('surpassed_self', sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('workout_session', schema=None) as batch_op:
        batch_op.drop_column('surpassed_self')
