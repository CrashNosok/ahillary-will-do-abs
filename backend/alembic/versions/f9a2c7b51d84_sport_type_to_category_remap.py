"""sport: rename type -> category + remap cardio/skill (M1·B14)

Cutover каталога дисциплин с тройки SportType (strength/cardio/skill) на таксономию
SportCategory (M1·B13). Колонку sport.type переименовываем в sport.category и
ремапим значения существующих строк: cardio→endurance, skill→action (strength без
изменений). Колонка — plain VARCHAR без CHECK/native-enum, валидация на уровне
Pydantic (SportCategory), поэтому достаточно rename + UPDATE значений.

Revision ID: f9a2c7b51d84
Revises: e2d7c9a4b815
Create Date: 2026-06-25 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f9a2c7b51d84'
down_revision: Union[str, Sequence[str], None] = 'e2d7c9a4b815'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('sport', schema=None) as batch_op:
        batch_op.alter_column('type', new_column_name='category')
    op.execute("UPDATE sport SET category = 'endurance' WHERE category = 'cardio'")
    op.execute("UPDATE sport SET category = 'action' WHERE category = 'skill'")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("UPDATE sport SET category = 'cardio' WHERE category = 'endurance'")
    op.execute("UPDATE sport SET category = 'skill' WHERE category = 'action'")
    with op.batch_alter_table('sport', schema=None) as batch_op:
        batch_op.alter_column('category', new_column_name='type')
