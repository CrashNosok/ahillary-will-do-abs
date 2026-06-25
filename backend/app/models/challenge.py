"""Челлендж (M6·B30): задание/вызов по виду спорта, который заводят пользователи.

Привязан к дисциплине через FK sport_id и к автору через FK creator_user_id
(оба NOT NULL, индексированы). title и description обязательны — заголовок вызова
и что именно нужно сделать (sport_recommendation так же требует title+body).
is_base отделяет базовые (встроенные) челленджи от заведённых пользователем —
bool с дефолтом False, как Sport.is_global. Роутера/UI пока нет (только модель).
"""

from sqlmodel import Field, SQLModel


class Challenge(SQLModel, table=True):
    __tablename__ = "challenge"

    id: int | None = Field(default=None, primary_key=True)
    sport_id: int = Field(foreign_key="sport.id", index=True)
    creator_user_id: int = Field(foreign_key="user.id", index=True)  # автор челленджа
    title: str  # заголовок вызова, обязателен
    description: str  # что нужно сделать, обязательно
    is_base: bool = Field(default=False)  # базовый (встроенный) vs пользовательский
