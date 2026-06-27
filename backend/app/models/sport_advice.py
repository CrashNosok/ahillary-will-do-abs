"""ИИ-рекомендация по конкретному виду спорта: как двигаться к целям по упражнениям и
осваивать навыки из плана. Храним последнюю на пару (user_id, sport_id) — upsert, без истории
(трекер личный, нужен актуальный совет). Текст в markdown, генерит LLM по срезу данных вида.
"""

import datetime as dt

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models._time import utcnow


class SportAdvice(SQLModel, table=True):
    __tablename__ = "sport_advice"
    __table_args__ = (
        UniqueConstraint("user_id", "sport_id", name="uq_sport_advice_user_sport"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    sport_id: int = Field(foreign_key="sport.id", index=True)
    text: str  # markdown-совет от модели
    model: str  # какая модель сгенерировала (для отладки)
    created_at: dt.datetime = Field(default_factory=utcnow)
