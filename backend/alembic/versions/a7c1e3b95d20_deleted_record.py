"""deleted_record — архив удалённых данных (soft-delete «Очистить»)

Revision ID: a7c1e3b95d20
Revises: f4a9c2d7e810
Create Date: 2026-06-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c1e3b95d20'
down_revision: Union[str, Sequence[str], None] = 'f4a9c2d7e810'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'deleted_record',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('source_table', sa.String(), nullable=False),
        sa.Column('payload', sa.String(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_deleted_record_user_id', 'deleted_record', ['user_id'])
    op.create_index('ix_deleted_record_source_table', 'deleted_record', ['source_table'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_deleted_record_source_table', table_name='deleted_record')
    op.drop_index('ix_deleted_record_user_id', table_name='deleted_record')
    op.drop_table('deleted_record')
