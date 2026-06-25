"""sport_level table (M5·B23)

Новая таблица sport_level(id, sport_id, code, label, rank, description?) — ступени/грейды
прогресса внутри вида спорта. FK на sport.id. Составные уникальные ограничения
(sport_id, rank) и (sport_id, code): ступени одной дисциплины не дублируются ни по
порядку, ни по коду. Цель ссылки UserSport.current_level_id (пока nullable int без FK).
Свежая таблица — обычный create_table/drop_table.

Revision ID: b8d3f0a25e17
Revises: d7e9f2a4c618
Create Date: 2026-06-25 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # SQLModel-типы (AutoString и пр.) в autogenerate-миграциях


# revision identifiers, used by Alembic.
revision: str = 'b8d3f0a25e17'
down_revision: Union[str, Sequence[str], None] = 'd7e9f2a4c618'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'sport_level',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sport_id', sa.Integer(), nullable=False),
        sa.Column('code', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('label', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(['sport_id'], ['sport.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sport_id', 'rank', name='uq_sport_level_sport_rank'),
        sa.UniqueConstraint('sport_id', 'code', name='uq_sport_level_sport_code'),
    )
    op.create_index(op.f('ix_sport_level_sport_id'), 'sport_level', ['sport_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_sport_level_sport_id'), table_name='sport_level')
    op.drop_table('sport_level')
