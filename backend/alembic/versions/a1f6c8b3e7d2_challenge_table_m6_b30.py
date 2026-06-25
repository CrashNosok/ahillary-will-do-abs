"""challenge table M6·B30

Новая таблица challenge(id, sport_id, creator_user_id, title, description,
is_base) — задания/вызовы по виду спорта, заводимые пользователями. FK sport_id
на sport.id и creator_user_id на user.id (оба NOT NULL, индексированы). title и
description обязательны. is_base — bool NOT NULL (server_default 0): базовый
встроенный челлендж vs пользовательский. Свежая таблица — create_table/drop_table.

Revision ID: a1f6c8b3e7d2
Revises: c3492fe0b4d2
Create Date: 2026-06-25 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # SQLModel-типы (AutoString и пр.) в autogenerate-миграциях


# revision identifiers, used by Alembic.
revision: str = 'a1f6c8b3e7d2'
down_revision: Union[str, Sequence[str], None] = 'c3492fe0b4d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('challenge',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('sport_id', sa.Integer(), nullable=False),
    sa.Column('creator_user_id', sa.Integer(), nullable=False),
    sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('is_base', sa.Boolean(), nullable=False, server_default=sa.text('0')),
    sa.ForeignKeyConstraint(['creator_user_id'], ['user.id'], ),
    sa.ForeignKeyConstraint(['sport_id'], ['sport.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('challenge', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_challenge_creator_user_id'), ['creator_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_challenge_sport_id'), ['sport_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('challenge', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_challenge_sport_id'))
        batch_op.drop_index(batch_op.f('ix_challenge_creator_user_id'))

    op.drop_table('challenge')
