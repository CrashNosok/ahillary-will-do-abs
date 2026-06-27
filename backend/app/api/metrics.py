"""Реестр метрик-параметров для фронта — единый источник правды (services/metrics.py).

GET /metrics/registry отдаёт список метрик (ключ/подпись/единица/группа/направление), по
которому фронт строит форму целей в «Мой кабинет» и подписи целевых линий. Список может
меняться — фронт забирает его с бэка, а не дублирует у себя.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.services.metrics import REGISTRY, current_metric_values

router = APIRouter(prefix="/metrics", tags=["metrics"])

SessionDep = Annotated[Session, Depends(get_session)]


class MetricSpecOut(BaseModel):
    key: str
    label: str
    unit: str
    group: str
    good_dir: str


@router.get("/registry")
def get_metric_registry(_: CurrentUser) -> list[MetricSpecOut]:
    """Полный реестр метрик-параметров в порядке групп (состав тела → обхваты → дневные)."""
    return [
        MetricSpecOut(key=m.key, label=m.label, unit=m.unit, group=m.group, good_dir=m.good_dir)
        for m in REGISTRY
    ]


@router.get("/current")
def get_current_metrics(session: SessionDep, user: CurrentUser) -> dict[str, float]:
    """Текущие показатели владельца {ключ_реестра: значение} — дефолт для формы целей.

    Тело — последний замер, дневные нормы — среднее за окно. Метрики без данных опущены.
    """
    return current_metric_values(session, user_id=user.id)
