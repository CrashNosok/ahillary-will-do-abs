"""body-кластер: user_id FK на body_measurement, inbody_measurement, progress_photo, hr_zones (M0·B4)

Изоляция данных по пользователю: в таблицы body-кластера добавляем user_id (FK на
user.id). SQLite не умеет ALTER ADD COLUMN с NOT NULL+FK напрямую, поэтому идём в три
фазы через op.batch_alter_table:
  1) добавляем nullable user_id;
  2) backfill существующих строк минимальным user.id (единственный сид-юзер);
  3) делаем колонку NOT NULL + индекс + внешний ключ.

Revision ID: a4c2e8f1b693
Revises: f3b8a2c9e571
Create Date: 2026-06-25 03:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4c2e8f1b693'
down_revision: Union[str, Sequence[str], None] = 'f3b8a2c9e571'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Кластер тела: таблицы-владельцы замеров/фото/зон (карточка M0·B4).
_TABLES = ("body_measurement", "inbody_measurement", "progress_photo", "hr_zones")


def upgrade() -> None:
    """Upgrade schema."""
    for table in _TABLES:
        # 1) nullable-колонка — добавляется без ограничений.
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        # 2) backfill: все существующие строки получают минимальный id пользователя.
        op.execute(
            f"UPDATE {table} SET user_id = (SELECT MIN(id) FROM user) WHERE user_id IS NULL"
        )
        # 3) NOT NULL + индекс + FK (батч пересобирает таблицу — для SQLite это и есть способ).
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column('user_id', existing_type=sa.Integer(), nullable=False)
            batch_op.create_index(op.f(f'ix_{table}_user_id'), ['user_id'], unique=False)
            batch_op.create_foreign_key(
                f'fk_{table}_user_id_user', 'user', ['user_id'], ['id']
            )


def downgrade() -> None:
    """Downgrade schema."""
    for table in _TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_index(op.f(f'ix_{table}_user_id'))
            batch_op.drop_column('user_id')
