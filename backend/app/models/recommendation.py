"""Рекомендация LLM (S1.2): сохранённый ответ модели по цели пользователя.

Поля заданы карточкой: created_at, model (имя модели), input_snapshot_json (срез данных,
поданных в промпт), output_json (структурированный ответ), raw_text (сырой текст), goal_id
(FK на smart_goal — к какой цели относится). JSON-поля гибкие: схема промпта/ответа меняется.

generation_ms (S4.9) — сколько миллисекунд заняла генерация (вызов модели + парс). Nullable:
у записей до S4.9 его нет — UI тогда показывает только модель.
"""

import datetime as dt
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.models._time import utcnow


class Recommendation(SQLModel, table=True):
    __tablename__ = "recommendation"

    id: int | None = Field(default=None, primary_key=True)
    created_at: dt.datetime = Field(default_factory=utcnow)
    model: str  # имя LLM-модели, сгенерировавшей рекомендацию
    input_snapshot_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    output_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    raw_text: str | None = None
    goal_id: int | None = Field(default=None, foreign_key="smart_goal.id", index=True)
    generation_ms: int | None = Field(default=None)  # длительность генерации, мс (S4.9)
