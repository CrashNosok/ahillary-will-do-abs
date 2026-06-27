"""smart_goal: единая карта целей target_metrics_json + бэкфилл из легаси-полей

Добавляет JSON-колонку target_metrics_json (единый источник правды для целей по реестру
метрик) и заполняет её для существующих целей из target_weight_kg/target_body_fat_pct и
target_measurements_json. Ключи приводятся к колонкам БД через LEGACY_KEY_MAP (чинит
исторический hips → glutes_cm и укороченные waist/chest → *_cm, иначе цель терялась).

Идемпотентно/null-safe: пустой target_measurements_json и отсутствие легаси-значений дают
{}; колонка остаётся nullable. Старые колонки НЕ удаляем (обратная совместимость).

Revision ID: b7e3c1a9f240
Revises: a9e2f7c3d418
Create Date: 2026-06-27 13:00:00.000000

"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7e3c1a9f240'
down_revision: Union[str, Sequence[str], None] = 'a9e2f7c3d418'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Инлайн-копия маппинга/реестра (миграция самодостаточна, без импорта app-кода).
_LEGACY_KEY_MAP = {
    "hips": "glutes_cm",
    "waist": "waist_cm",
    "belly": "belly_cm",
    "chest": "chest_cm",
    "shoulders": "shoulders_cm",
    "glutes": "glutes_cm",
}
_CANONICAL_KEYS = {
    "weight_kg", "body_fat_pct", "muscle_mass_kg", "visceral_fat", "water",
    "waist_cm", "belly_cm", "chest_cm", "shoulders_cm", "biceps_l_cm", "biceps_r_cm",
    "glutes_cm", "calf_l_cm", "calf_r_cm",
    "kcal_in", "protein_g", "fat_g", "carb_g", "steps", "deficit_kcal",
}


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def upgrade() -> None:
    op.add_column("smart_goal", sa.Column("target_metrics_json", sa.JSON(), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, target_weight_kg, target_body_fat_pct, target_measurements_json "
            "FROM smart_goal"
        )
    ).fetchall()
    for row in rows:
        goal_id, weight, body_fat, measurements_raw = row
        merged: dict[str, float] = {}
        if weight is not None:
            merged["weight_kg"] = float(weight)
        if body_fat is not None:
            merged["body_fat_pct"] = float(body_fat)
        if measurements_raw:
            data = measurements_raw if isinstance(measurements_raw, dict) else json.loads(measurements_raw)
            for raw_key, raw_val in (data or {}).items():
                key = _LEGACY_KEY_MAP.get(raw_key, raw_key)
                val = _to_float(raw_val)
                if key in _CANONICAL_KEYS and val is not None:
                    merged[key] = val
        bind.execute(
            sa.text("UPDATE smart_goal SET target_metrics_json = :j WHERE id = :id"),
            {"j": json.dumps(merged), "id": goal_id},
        )


def downgrade() -> None:
    op.drop_column("smart_goal", "target_metrics_json")
