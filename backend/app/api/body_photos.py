"""Фото прогресса тела (вкладка «Ввод данных → Фото»): загрузка + галерея + отдача файла.

Храним только сам файл на диске (data/uploads/progress/<date>_<uuid>.<ext>) и путь в
progress_photo; байты в БД не держим — как у InBody/видео-пруфов. Несколько фото на день
разрешены. Роуты под сессией (CurrentUser) — приложение однопользовательское. Контролируемые
ошибки: пустой файл / неподдерживаемый формат → 422; нет фото / файла на диске → 404.
"""

import datetime as dt
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import CurrentUser
from app.core import db
from app.core.db import get_session
from app.models.body import ProgressPhoto

router = APIRouter(prefix="/body-photos", tags=["body"])

SessionDep = Annotated[Session, Depends(get_session)]

# content-type → расширение файла. Ключ — для определения по MIME, значения множества — для fallback по имени.
_CT_SUFFIX = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
_EXT_OK = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


class ProgressPhotoOut(BaseModel):
    """Метаданные фото для галереи (без пути к файлу — файл отдаёт GET /body-photos/{id})."""

    id: int
    date: dt.date
    notes: str | None
    uploaded_at: dt.datetime


def _resolve_suffix(file: UploadFile) -> str | None:
    """Расширение по content-type, иначе по имени файла. None → формат не поддержан."""
    suffix = _CT_SUFFIX.get(file.content_type or "")
    if suffix is None and file.filename:
        ext = Path(file.filename).suffix.lower()
        if ext in _EXT_OK:
            suffix = ".jpg" if ext == ".jpeg" else ext
    return suffix


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_photo(
    session: SessionDep,
    _: CurrentUser,
    file: Annotated[UploadFile, File()],
    date: Annotated[dt.date | None, Form()] = None,
    notes: Annotated[str | None, Form()] = None,
) -> ProgressPhotoOut:
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Пустой файл изображения"
        )
    suffix = _resolve_suffix(file)
    if suffix is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Поддерживаются изображения JPEG, PNG, WebP, GIF",
        )

    day = date or dt.date.today()
    dest = db.progress_dir() / f"{day.isoformat()}_{uuid.uuid4().hex[:8]}{suffix}"
    dest.write_bytes(image_bytes)

    photo = ProgressPhoto(
        date=day,
        source_image_path=str(dest.relative_to(db.BACKEND_DIR)),
        notes=notes,
    )
    session.add(photo)
    session.commit()
    session.refresh(photo)
    return ProgressPhotoOut(id=photo.id, date=photo.date, notes=photo.notes, uploaded_at=photo.uploaded_at)


@router.get("")
def list_photos(
    session: SessionDep,
    _: CurrentUser,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> list[ProgressPhotoOut]:
    """Список фото для галереи (новые сверху). Опциональный диапазон дат."""
    stmt = select(ProgressPhoto)
    if start is not None:
        stmt = stmt.where(ProgressPhoto.date >= start)
    if end is not None:
        stmt = stmt.where(ProgressPhoto.date <= end)
    stmt = stmt.order_by(ProgressPhoto.date.desc(), ProgressPhoto.id.desc())
    rows = session.exec(stmt).all()
    return [
        ProgressPhotoOut(id=r.id, date=r.date, notes=r.notes, uploaded_at=r.uploaded_at) for r in rows
    ]


@router.get("/{photo_id}")
def get_photo(photo_id: int, session: SessionDep, _: CurrentUser) -> FileResponse:
    """Отдаёт сам файл фото (media_type выводится из расширения)."""
    photo = session.get(ProgressPhoto, photo_id)
    if photo is None or not photo.source_image_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Фото не найдено")
    path = Path(photo.source_image_path)
    if not path.is_absolute():
        path = db.BACKEND_DIR / path
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл фото отсутствует")
    return FileResponse(path)
