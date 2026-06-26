"""Связка «пользователь ↔ вид спорта» (M2·B19): какие дисциплины ведёт пользователь.

user_sport — many-to-many между user и sport с атрибутами связи. Составной PK
(user_id, sport_id): одну дисциплину пользователь линкует не более одного раза, поэтому
повторный link упирается в PK (409), а не плодит дубли.

current_level_id — опциональная ссылка на «текущий уровень» пользователя в дисциплине.
Отдельной таблицы уровней в проекте пока нет (level — строковое поле Achievement,
AthleteLevel — enum), поэтому колонка хранится как nullable int без FK: forward-compat
под будущую таблицу уровней. rating — опциональная самооценка/рейтинг по дисциплине.
"""

import datetime as dt

from sqlmodel import Field, SQLModel

from app.models._time import utcnow


class UserSport(SQLModel, table=True):
    __tablename__ = "user_sport"

    # Составной PK (user_id, sport_id) — связка уникальна на пару, дубль линка невозможен.
    user_id: int = Field(foreign_key="user.id", primary_key=True)
    sport_id: int = Field(foreign_key="sport.id", primary_key=True)
    # Текущий уровень пользователя в дисциплине: nullable int без FK (таблицы уровней пока
    # нет — см. модуль-docstring). rating — опциональный рейтинг/самооценка, дробный допустим.
    current_level_id: int | None = Field(default=None)
    rating: float | None = Field(default=None)
    joined_at: dt.datetime = Field(default_factory=utcnow)
    # Мягкая отвязка: персональные данные (уровень/рейтинг) живут на связке и НЕ удаляются при
    # отвязке — unlink лишь снимает флаг. Повторная привязка восстанавливает прежний уровень.
    linked: bool = Field(default=True)
