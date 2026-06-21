"""sport: add type, rename notes -> description (S3.1)

Карточка S3.1 задаёт sport(name, type, description). Baseline создал sport(name, notes)
как скелет (S1.2) — таблица пустая, в API/seed не пишется. Здесь добавляем валидируемый
type и переименовываем неиспользуемый notes в description под формулировку карточки.

Revision ID: 7b2e9d4a1c83
Revises: c78441d536ea
Create Date: 2026-06-21 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # SQLModel-типы (AutoString и пр.)


# revision identifiers, used by Alembic.
revision: str = '7b2e9d4a1c83'
down_revision: Union[str, Sequence[str], None] = 'c78441d536ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('sport', schema=None) as batch_op:
        # server_default — страховка миграции (sport пустой; API всегда шлёт type).
        batch_op.add_column(
            sa.Column(
                'type',
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=False,
                server_default=sa.text("'strength'"),
            )
        )
        batch_op.alter_column('notes', new_column_name='description')


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('sport', schema=None) as batch_op:
        batch_op.alter_column('description', new_column_name='notes')
        batch_op.drop_column('type')
