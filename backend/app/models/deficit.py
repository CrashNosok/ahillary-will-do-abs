"""Дневной дефицит калорий (S1.1): deficit = eaten - burn, посчитанный за день."""

import datetime as dt

from sqlmodel import Field, SQLModel

from app.models._time import utcnow

STATUS_COMPLETE = "полный"
STATUS_INCOMPLETE = "неполный день"


class DeficitDay(SQLModel, table=True):
    __tablename__ = "deficit_day"

    # Владелец дня (M0·B7): составной PK (user_id, date) — один расчёт на день У КАЖДОГО
    # пользователя. Раньше PK был только date → один дефицит на дату ГЛОБАЛЬНО, и recompute
    # одного аккаунта перетирал день другого (межаккаунтная коллизия). user_id ещё и FK на user.
    user_id: int = Field(foreign_key="user.id", primary_key=True, index=True)
    date: dt.date = Field(primary_key=True)  # один расчёт на день (в пределах user_id)
    eaten_kcal: int | None = None
    burn_kcal: int | None = None
    deficit_kcal: int | None = None
    computed_at: dt.datetime = Field(default_factory=utcnow)

    @property
    def status(self) -> str:
        """«полный» когда есть оба источника, иначе «неполный день» (S1.12).

        Производное от eaten/burn, а не колонка: deficit_kcal у неполного дня остаётся
        None (без ложного нуля), поэтому статус однозначно следует из данных. Так
        запись совместима с уже существующей таблицей без миграции (Alembic — Sprint 2).
        """
        complete = self.eaten_kcal is not None and self.burn_kcal is not None
        return STATUS_COMPLETE if complete else STATUS_INCOMPLETE
