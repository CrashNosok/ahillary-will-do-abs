"""challenge_sponsor table M6·B33

Новая таблица challenge_sponsor(id, challenge_id, sponsor_id, amount, currency) —
спонсорство челленджа. FK challenge_id на challenge.id и sponsor_id на sponsor.id (оба
NOT NULL, индексированы). amount — Numeric(12,2) NOT NULL (деньги, не float); currency —
строка NOT NULL (код валюты ISO 4217). unique (challenge_id, sponsor_id): спонсор
поддерживает челлендж не более одного раза. Свежая таблица — create_table/drop_table.

Revision ID: d5e9a3c1f042
Revises: f1a7c2d9b8e4
Create Date: 2026-06-25 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # SQLModel-типы (AutoString и пр.) в autogenerate-миграциях


# revision identifiers, used by Alembic.
revision: str = 'd5e9a3c1f042'
down_revision: Union[str, Sequence[str], None] = 'f1a7c2d9b8e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('challenge_sponsor',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('challenge_id', sa.Integer(), nullable=False),
    sa.Column('sponsor_id', sa.Integer(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('currency', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.ForeignKeyConstraint(['challenge_id'], ['challenge.id'], ),
    sa.ForeignKeyConstraint(['sponsor_id'], ['sponsor.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('challenge_id', 'sponsor_id', name='uq_challenge_sponsor_challenge_sponsor')
    )
    with op.batch_alter_table('challenge_sponsor', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_challenge_sponsor_challenge_id'), ['challenge_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_challenge_sponsor_sponsor_id'), ['sponsor_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('challenge_sponsor', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_challenge_sponsor_sponsor_id'))
        batch_op.drop_index(batch_op.f('ix_challenge_sponsor_challenge_id'))

    op.drop_table('challenge_sponsor')
