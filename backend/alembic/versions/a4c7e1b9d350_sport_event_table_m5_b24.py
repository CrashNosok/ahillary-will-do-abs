"""sport_event table (M5·B24)

Новая таблица sport_event(id, sport_id, title, description, location, starts_on,
ends_on, url) — события/соревнования по виду спорта. FK на sport.id. title и starts_on
обязательны; ends_on (None — однодневное), description/location/url — необязательны.
Глобальный каталог без user-скоупа. Свежая таблица — обычный create_table/drop_table.

Revision ID: a4c7e1b9d350
Revises: b8d3f0a25e17
Create Date: 2026-06-25 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # SQLModel-типы (AutoString и пр.) в autogenerate-миграциях


# revision identifiers, used by Alembic.
revision: str = 'a4c7e1b9d350'
down_revision: Union[str, Sequence[str], None] = 'b8d3f0a25e17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'sport_event',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sport_id', sa.Integer(), nullable=False),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('location', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('starts_on', sa.Date(), nullable=False),
        sa.Column('ends_on', sa.Date(), nullable=True),
        sa.Column('url', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(['sport_id'], ['sport.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_sport_event_sport_id'), 'sport_event', ['sport_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_sport_event_sport_id'), table_name='sport_event')
    op.drop_table('sport_event')
