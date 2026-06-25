"""sport: add slug, long_description, is_global (M5·B22)

Карточка M5·B22 «rich-поля» обогащает каталог дисциплин: slug — ЧПУ-идентификатор
(уникальный, авто из name на создании), long_description — развёрнутое описание,
is_global — встроенная (общая) дисциплина vs заведённая пользователем.
Таблица sport в API наполняется только через CRUD; server_default страхует пустые/старые строки.

Revision ID: d7e9f2a4c618
Revises: 162efaa3629d
Create Date: 2026-06-25 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # SQLModel-типы (AutoString и пр.)


# revision identifiers, used by Alembic.
revision: str = 'd7e9f2a4c618'
down_revision: Union[str, Sequence[str], None] = '162efaa3629d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('sport', schema=None) as batch_op:
        batch_op.add_column(sa.Column('slug', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(
            sa.Column('long_description', sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )
        # server_default — страховка для существующих строк (булев флаг NOT NULL).
        batch_op.add_column(
            sa.Column('is_global', sa.Boolean(), nullable=False, server_default=sa.text('0'))
        )
        batch_op.create_index(batch_op.f('ix_sport_slug'), ['slug'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('sport', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sport_slug'))
        batch_op.drop_column('is_global')
        batch_op.drop_column('long_description')
        batch_op.drop_column('slug')
