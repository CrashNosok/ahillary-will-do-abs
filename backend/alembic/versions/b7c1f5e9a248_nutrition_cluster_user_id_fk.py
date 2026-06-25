"""nutrition-кластер: user_id FK на food_entry, smart_goal, recommendation, deficit_day (M0·B5)

Изоляция данных по пользователю: в таблицы кластера питания/целей/рекомендаций добавляем
user_id (FK на user.id). SQLite не умеет ALTER ADD COLUMN с NOT NULL+FK напрямую, поэтому
идём в три фазы через op.batch_alter_table:
  1) добавляем nullable user_id;
  2) backfill существующих строк минимальным user.id (единственный сид-юзер);
  3) делаем колонку NOT NULL + индекс + внешний ключ.

Revision ID: b7c1f5e9a248
Revises: a4c2e8f1b693
Create Date: 2026-06-25 04:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c1f5e9a248'
down_revision: Union[str, Sequence[str], None] = 'a4c2e8f1b693'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Кластер питания/целей: таблицы-владельцы записей дневника, целей, рекомендаций и
# дневного дефицита (карточка M0·B5).
_TABLES = ("food_entry", "smart_goal", "recommendation", "deficit_day")


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
