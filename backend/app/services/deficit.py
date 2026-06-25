"""Пересчёт дневного дефицита калорий (S1.12).

deficit = eaten_kcal (сумма food_entry за дату) − burn_kcal (activity_day.total_kcal).
`recompute` вызывается при изменении еды/активности и сохраняет результат в deficit_day
(идемпотентно по дню — upsert).

Источник считается отсутствующим, если за день нет ни одной записи food_entry (eaten=None)
или нет activity_day / total_kcal (burn=None). Тогда deficit_kcal остаётся None — без
ложного нуля (критерий приёмки S1.12), а DeficitDay.status отдаёт «неполный день».
Пустой приём с нулевыми ккал (записи есть, сумма 0) — это валидный 0, не пропуск.
"""

import datetime as dt

from sqlmodel import Session, select

from app.models._time import utcnow
from app.models.activity import ActivityDay
from app.models.deficit import DeficitDay
from app.models.nutrition import FoodEntry


def _eaten_kcal(date: dt.date, session: Session) -> int | None:
    """Сумма kcal всех food_entry за день. Нет ни одной записи → None (источник отсутствует)."""
    kcals = session.exec(select(FoodEntry.kcal).where(FoodEntry.date == date)).all()
    if not kcals:
        return None
    return round(sum(k or 0.0 for k in kcals))


def _burn_kcal(date: dt.date, session: Session) -> int | None:
    """burn = activity_day.total_kcal за день. Нет записи или total_kcal=None → None."""
    day = session.get(ActivityDay, date)
    return day.total_kcal if day else None


def recompute(date: dt.date, session: Session, user_id: int) -> DeficitDay:
    """Пересчитать и сохранить дефицит за день; вернуть запись deficit_day.

    deficit_kcal считается только когда оба источника есть; иначе остаётся None
    (без ложного нуля) и статус — «неполный день». Upsert по дате: повторный вызов
    обновляет ту же запись, а не плодит дубли. `user_id` — владелец дня (M0·B5):
    проставляется на запись (NOT NULL FK на user.id).
    """
    eaten = _eaten_kcal(date, session)
    burn = _burn_kcal(date, session)
    deficit = eaten - burn if eaten is not None and burn is not None else None

    row = session.get(DeficitDay, date) or DeficitDay(date=date, user_id=user_id)
    row.user_id = user_id
    row.eaten_kcal = eaten
    row.burn_kcal = burn
    row.deficit_kcal = deficit
    row.computed_at = utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
