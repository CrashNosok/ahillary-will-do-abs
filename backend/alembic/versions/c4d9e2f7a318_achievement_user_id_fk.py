"""achievement: user_id FK на achievement (M0·B6)

Изоляция данных по пользователю: в таблицу ачивок добавляем user_id (FK на user.id).
SQLite не умеет ALTER ADD COLUMN с NOT NULL+FK напрямую, поэтому идём в три фазы через
op.batch_alter_table:
  1) добавляем nullable user_id;
  2) backfill существующих строк минимальным user.id (единственный сид-юзер);
  3) делаем колонку NOT NULL + индекс + внешний ключ.

achievement_proof владельца не получает — он принадлежит пользователю транзитивно через
achievement_id (как дочерние таблицы workout-кластера через session_id).

Revision ID: c4d9e2f7a318
Revises: b7c1f5e9a248
Create Date: 2026-06-25 04:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d9e2f7a318'
down_revision: Union[str, Sequence[str], None] = 'b7c1f5e9a248'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Кластер ачивок: владелец нужен только таблице-цели achievement (M0·B6).
_TABLE = "achievement"


def upgrade() -> None:
    """Upgrade schema."""
    # 1) nullable-колонка — добавляется без ограничений.
    with op.batch_alter_table(_TABLE, schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
    # 2) backfill: все существующие строки получают минимальный id пользователя.
    op.execute(
        f"UPDATE {_TABLE} SET user_id = (SELECT MIN(id) FROM user) WHERE user_id IS NULL"
    )
    # 3) NOT NULL + индекс + FK (батч пересобирает таблицу — для SQLite это и есть способ).
    with op.batch_alter_table(_TABLE, schema=None) as batch_op:
        batch_op.alter_column('user_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_index(op.f(f'ix_{_TABLE}_user_id'), ['user_id'], unique=False)
        batch_op.create_foreign_key(
            f'fk_{_TABLE}_user_id_user', 'user', ['user_id'], ['id']
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table(_TABLE, schema=None) as batch_op:
        batch_op.drop_index(op.f(f'ix_{_TABLE}_user_id'))
        batch_op.drop_column('user_id')
