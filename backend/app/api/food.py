"""Импорт дневника питания из CSV: превью + сохранение (S1.8).

Две точки входа поверх парсера FatSecret (services/fatsecret.py):
- POST /import/food/preview — разобрать загруженный CSV и вернуть превью (день,
  приёмы, итоги) БЕЗ записи в БД. UI показывает разобранный день до сохранения.
- POST /import/food — разобрать и сохранить под общим import_id. Идемпотентно по
  дню (replace_day): повторная загрузка того же дня заменяет записи, не дублируя.

Обе принимают multipart-файл `file`. Нераспознанный CSV (нет даты дня) → 422.
Все роуты под сессией (CurrentUser) — приложение однопользовательское.
"""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlmodel import Session

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.services.fatsecret import (
    DiaryImport,
    Totals,
    import_food_diary,
    parse_diary,
    sum_totals,
)

router = APIRouter(prefix="/import", tags=["import"])

SessionDep = Annotated[Session, Depends(get_session)]


class TotalsOut(BaseModel):
    kcal: float
    fat_g: float
    carb_g: float
    protein_g: float

    @classmethod
    def of(cls, t: Totals) -> "TotalsOut":
        return cls(kcal=t.kcal, fat_g=t.fat_g, carb_g=t.carb_g, protein_g=t.protein_g)


class ProductOut(BaseModel):
    product_name: str
    portion_raw: str | None
    kcal: float | None
    protein_g: float | None
    fat_g: float | None
    carb_g: float | None


class MealOut(BaseModel):
    meal: str
    products: list[ProductOut]
    totals: TotalsOut


class DiaryPreview(BaseModel):
    """Разобранный день для UI: дата, приёмы с продуктами и посчитанные итоги.

    `saved` отличает превью (False) от результата сохранения (True); `import_id`
    проставлен только после записи.
    """

    date: dt.date
    meals: list[MealOut]
    totals: TotalsOut
    product_count: int
    saved: bool
    import_id: str | None = None


def _to_preview(parsed: DiaryImport, *, saved: bool, import_id: str | None) -> DiaryPreview:
    """Собрать превью из разбора: продукты группируются по приёму в порядке появления.

    Итоги приёмов и дня считаем из самих продуктов (а не заявленных в отчёте),
    чтобы UI показывал ровно то, что будет сохранено.
    """
    grouped: dict[str, list[ProductOut]] = {}
    for entry in parsed.entries:
        grouped.setdefault(entry.meal, []).append(
            ProductOut(
                product_name=entry.product_name,
                portion_raw=entry.portion_raw,
                kcal=entry.kcal,
                protein_g=entry.protein_g,
                fat_g=entry.fat_g,
                carb_g=entry.carb_g,
            )
        )
    meals = [
        MealOut(
            meal=meal,
            products=products,
            totals=TotalsOut.of(sum_totals([e for e in parsed.entries if e.meal == meal])),
        )
        for meal, products in grouped.items()
    ]
    return DiaryPreview(
        date=parsed.date,
        meals=meals,
        totals=TotalsOut.of(sum_totals(parsed.entries)),
        product_count=len(parsed.entries),
        saved=saved,
        import_id=import_id,
    )


async def _read_diary(file: UploadFile) -> DiaryImport:
    """Прочитать загрузку и разобрать; нераспознанный CSV → 422 с понятным detail."""
    raw = await file.read()
    try:
        return parse_diary(raw, file.filename)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Не удалось разобрать CSV: {exc}",
        ) from exc


@router.post("/food/preview")
async def preview_food(
    session: SessionDep,
    _: CurrentUser,
    file: Annotated[UploadFile, File()],
) -> DiaryPreview:
    parsed = await _read_diary(file)
    return _to_preview(parsed, saved=False, import_id=None)


@router.post("/food", status_code=status.HTTP_201_CREATED)
async def import_food(
    session: SessionDep,
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
    # Необязательная дата: записать дневник на выбранный в календаре день, а не из файла.
    date: Annotated[dt.date | None, Form()] = None,
) -> DiaryPreview:
    # import_food_diary сам парсит и пишет; идемпотентно по дню (replace_day).
    raw = await file.read()
    try:
        parsed = import_food_diary(
            raw,
            session,
            user_id=user.id,
            filename=file.filename,
            replace_day=True,
            override_date=date,
        )
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Не удалось разобрать CSV: {exc}",
        ) from exc
    import_id = parsed.entries[0].import_id if parsed.entries else None
    return _to_preview(parsed, saved=True, import_id=import_id)
