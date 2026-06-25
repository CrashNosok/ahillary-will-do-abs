"""challenge_participant table M6·B31

Новая таблица challenge_participant(id, challenge_id, user_id, status) — участие
пользователя в челлендже. FK challenge_id на challenge.id и user_id на user.id (оба
NOT NULL, индексированы). status — строка NOT NULL (server_default 'active'): статус
участия (active/completed/abandoned). unique (challenge_id, user_id): пользователь
участвует в челлендже не более одного раза. Свежая таблица — create_table/drop_table.

Revision ID: b2d8f4a6c1e9
Revises: a1f6c8b3e7d2
Create Date: 2026-06-25 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # SQLModel-типы (AutoString и пр.) в autogenerate-миграциях


# revision identifiers, used by Alembic.
revision: str = 'b2d8f4a6c1e9'
down_revision: Union[str, Sequence[str], None] = 'a1f6c8b3e7d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('challenge_participant',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('challenge_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=sa.text("'active'")),
    sa.ForeignKeyConstraint(['challenge_id'], ['challenge.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('challenge_id', 'user_id', name='uq_challenge_participant_challenge_user')
    )
    with op.batch_alter_table('challenge_participant', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_challenge_participant_challenge_id'), ['challenge_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_challenge_participant_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_challenge_participant_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('challenge_participant', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_challenge_participant_user_id'))
        batch_op.drop_index(batch_op.f('ix_challenge_participant_status'))
        batch_op.drop_index(batch_op.f('ix_challenge_participant_challenge_id'))

    op.drop_table('challenge_participant')
