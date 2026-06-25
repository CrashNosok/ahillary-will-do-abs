"""challenge_proof table M6·B32

Новая таблица challenge_proof(id, participant_id, video_path, thumbnail_path,
uploaded_at, notes) — видео-пруф участия в челлендже, клон achievement_proof по
participant_id. FK participant_id на challenge_participant.id (NOT NULL, индексирован);
video_path/thumbnail_path/notes nullable (в БД только пути на диск); uploaded_at —
DateTime NOT NULL (default на стороне приложения). Свежая таблица — create/drop.

Revision ID: f1a7c2d9b8e4
Revises: b2d8f4a6c1e9
Create Date: 2026-06-25 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # SQLModel-типы (AutoString и пр.) в autogenerate-миграциях


# revision identifiers, used by Alembic.
revision: str = 'f1a7c2d9b8e4'
down_revision: Union[str, Sequence[str], None] = 'b2d8f4a6c1e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('challenge_proof',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('participant_id', sa.Integer(), nullable=False),
    sa.Column('video_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('thumbnail_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('uploaded_at', sa.DateTime(), nullable=False),
    sa.Column('notes', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.ForeignKeyConstraint(['participant_id'], ['challenge_participant.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('challenge_proof', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_challenge_proof_participant_id'), ['participant_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('challenge_proof', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_challenge_proof_participant_id'))

    op.drop_table('challenge_proof')
