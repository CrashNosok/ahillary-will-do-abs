"""user: add display_name + is_active (M0·B2)

Карточка M0·B2 добавляет в профиль единственного пользователя два поля:
display_name (опциональное отображаемое имя) и is_active (флаг активности).
SQLite не умеет ALTER ADD COLUMN с ограничениями напрямую — идём через
op.batch_alter_table. is_active NOT NULL, поэтому добавляем с server_default
(true), чтобы существующая строка сид-юзера получила значение.

Revision ID: e1a7c4b9d260
Revises: c3d8f2a4e5b6
Create Date: 2026-06-25 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # SQLModel-типы (AutoString и пр.)


# revision identifiers, used by Alembic.
revision: str = 'e1a7c4b9d260'
down_revision: Union[str, Sequence[str], None] = 'c3d8f2a4e5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('display_name', sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true())
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('is_active')
        batch_op.drop_column('display_name')
