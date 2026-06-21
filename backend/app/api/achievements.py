"""Видео-пруфы ачивок (S5.4): загрузка видео + генерация превью.

POST /achievements/{achievement_id}/proofs — принимает файл видео (+ опц. notes),
кладёт его в data/videos/<achievement_id>/, генерит кадр-превью через ffmpeg и пишет
achievement_proof (пути к файлам + uploaded_at + notes; байты в БД не хранятся).
Роут под сессией (CurrentUser) — приложение однопользовательское. Контролируемые
ошибки: неизвестная ачивка → 404, пустой/нечитаемый файл → 422.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlmodel import Session

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.models.achievement import Achievement, AchievementProof
from app.services import achievement_proof as proof_service

router = APIRouter(prefix="/achievements", tags=["achievements"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.post("/{achievement_id}/proofs", status_code=status.HTTP_201_CREATED)
async def upload_proof(
    achievement_id: int,
    session: SessionDep,
    _: CurrentUser,
    file: Annotated[UploadFile, File()],
    notes: Annotated[str | None, Form()] = None,
) -> AchievementProof:
    if session.get(Achievement, achievement_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ачивка не найдена")
    video_bytes = await file.read()
    if not video_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Пустой файл видео"
        )
    try:
        return proof_service.save_proof(
            session, achievement_id, video_bytes, filename=file.filename, notes=notes
        )
    except proof_service.ThumbnailError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Не удалось сгенерировать превью из видео: {exc}",
        ) from exc
