"""Дневной ингест питания: одна строка food_entry = один съеденный продукт (S1.1).

Источник — экспорт FatSecret (см. docs/sample-formats.md): дата, приём, продукт,
порция (сырой текст + граммы) и нутриенты. import_id связывает строки одного импорта.
"""

import datetime as dt

from sqlmodel import Field, SQLModel

from app.models._time import utcnow


class FoodEntry(SQLModel, table=True):
    __tablename__ = "food_entry"

    id: int | None = Field(default=None, primary_key=True)
    # Владелец записи (M0·B5): изоляция данных по пользователю. NOT NULL + FK на user.id.
    user_id: int = Field(foreign_key="user.id", index=True)
    date: dt.date = Field(index=True)
    meal: str  # Завтрак / Обед / Ужин / Перекус
    product_name: str
    portion_raw: str | None = None  # сырой текст порции, напр. "300 г"
    portion_grams: float | None = None
    kcal: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    carb_g: float | None = None
    import_id: str | None = Field(default=None, index=True)
    # Момент внесения — для порядка заливки дня в календаре (категории в порядке появления).
    created_at: dt.datetime = Field(default_factory=utcnow)
