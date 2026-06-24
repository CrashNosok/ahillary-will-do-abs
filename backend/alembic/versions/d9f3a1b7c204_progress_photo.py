"""progress_photo: фото прогресса тела

Новая фича «Ввод данных → Фото»: храним путь к файлу на диске + дату + заметку.
Байты в БД не держим (как InBody/видео-пруфы). Дата индексируется для выборок галереи.

Revision ID: d9f3a1b7c204
Revises: b9e7d3a1f6c2
Create Date: 2026-06-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # SQLModel-типы (AutoString и пр.)


# revision identifiers, used by Alembic.
revision: str = 'd9f3a1b7c204'
down_revision: Union[str, Sequence[str], None] = 'b9e7d3a1f6c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'progress_photo',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('source_image_path', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('notes', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_progress_photo_date'), 'progress_photo', ['date'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_progress_photo_date'), table_name='progress_photo')
    op.drop_table('progress_photo')
