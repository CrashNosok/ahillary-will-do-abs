"""workout: минимальный лог (kind/duration/rpe) + медиа тренировки

Фича S3.11 «минимальный ручной ввод тренировки»: в workout_session добавляем
kind/duration_min/rpe (быстрый лог без таблиц подходов), и новую таблицу
workout_media (путь к фото/видео на диске, как progress_photo).

Revision ID: c3d8f2a4e5b6
Revises: d9f3a1b7c204
Create Date: 2026-06-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # SQLModel-типы (AutoString и пр.)


# revision identifiers, used by Alembic.
revision: str = 'c3d8f2a4e5b6'
down_revision: Union[str, Sequence[str], None] = 'd9f3a1b7c204'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('workout_session', sa.Column('kind', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('workout_session', sa.Column('duration_min', sa.Float(), nullable=True))
    op.add_column('workout_session', sa.Column('rpe', sa.Float(), nullable=True))
    op.create_table(
        'workout_media',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('media_path', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('media_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['workout_session.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_workout_media_session_id'), 'workout_media', ['session_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_workout_media_session_id'), table_name='workout_media')
    op.drop_table('workout_media')
    # SQLite не умеет DROP COLUMN напрямую — пересобираем таблицу через batch.
    with op.batch_alter_table('workout_session') as batch:
        batch.drop_column('rpe')
        batch.drop_column('duration_min')
        batch.drop_column('kind')
