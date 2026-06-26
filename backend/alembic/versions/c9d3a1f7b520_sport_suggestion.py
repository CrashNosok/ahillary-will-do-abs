"""sport_suggestion — заявки «предложить вид спорта» (очередь на ревью)

Revision ID: c9d3a1f7b520
Revises: b8f2d4a6c310
Create Date: 2026-06-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9d3a1f7b520'
down_revision: Union[str, Sequence[str], None] = 'b8f2d4a6c310'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'sport_suggestion',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('category', sa.String(), nullable=True),
        sa.Column('note', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sport_suggestion_user_id', 'sport_suggestion', ['user_id'])
    op.create_index('ix_sport_suggestion_status', 'sport_suggestion', ['status'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_sport_suggestion_status', table_name='sport_suggestion')
    op.drop_index('ix_sport_suggestion_user_id', table_name='sport_suggestion')
    op.drop_table('sport_suggestion')
