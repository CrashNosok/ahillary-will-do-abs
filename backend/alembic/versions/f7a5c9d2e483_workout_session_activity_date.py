"""workout_session: add activity_date FK -> activity_day (S3.9)

Карточка S3.9 «Связь тренировка ↔ день активности»: соотнести тренировку с Welltory-днём.
Добавляем workout_session.activity_date — nullable FK на activity_day.date. API проставляет
её автолинком при создании сессии (если за дату есть activity_day), иначе оставляет NULL.
Baseline (S1.2) создал workout_session без этой связи. Остальные поля не трогаем.

Revision ID: f7a5c9d2e483
Revises: e6f4b8a3d172
Create Date: 2026-06-21 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7a5c9d2e483'
down_revision: Union[str, Sequence[str], None] = 'e6f4b8a3d172'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('workout_session', schema=None) as batch_op:
        batch_op.add_column(sa.Column('activity_date', sa.Date(), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_workout_session_activity_date'), ['activity_date'], unique=False
        )
        batch_op.create_foreign_key(
            'fk_workout_session_activity_date_activity_day',
            'activity_day',
            ['activity_date'],
            ['date'],
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('workout_session', schema=None) as batch_op:
        batch_op.drop_constraint(
            'fk_workout_session_activity_date_activity_day', type_='foreignkey'
        )
        batch_op.drop_index(batch_op.f('ix_workout_session_activity_date'))
        batch_op.drop_column('activity_date')
