"""exercise: add notes (S3.2)

Карточка S3.2 задаёт exercise(sport_id, name, unit, notes). Baseline создал
exercise(sport_id, name, kind, unit) как скелет (S1.2). Здесь добавляем произвольную
заметку notes под формулировку карточки. kind (доalembic-овский) остаётся как есть —
вне scope этой карточки.

Revision ID: a3f1c9e7d215
Revises: 7b2e9d4a1c83
Create Date: 2026-06-21 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # SQLModel-типы (AutoString и пр.)


# revision identifiers, used by Alembic.
revision: str = 'a3f1c9e7d215'
down_revision: Union[str, Sequence[str], None] = '7b2e9d4a1c83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('exercise', schema=None) as batch_op:
        batch_op.add_column(sa.Column('notes', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('exercise', schema=None) as batch_op:
        batch_op.drop_column('notes')
