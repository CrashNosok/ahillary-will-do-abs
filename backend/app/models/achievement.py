"""Ачивки (S1.2): достижение по виду спорта + видео-пруфы.

achievement — цель-достижение (FK sport_id), поля из карточки: title, description, level,
status (locked/in_progress/unlocked), created_at, unlocked_at.
achievement_proof — пруф к ачивке (FK achievement_id): пути к видео и превью на диске
(в БД только пути — сами файлы на диске), время загрузки и заметки.
"""

import datetime as dt

from sqlmodel import Field, SQLModel

from app.models._time import utcnow


class Achievement(SQLModel, table=True):
    __tablename__ = "achievement"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)  # владелец ачивки (M0·B6)
    sport_id: int | None = Field(default=None, foreign_key="sport.id", index=True)
    title: str
    description: str | None = None
    level: str | None = None  # уровень/тир ачивки
    status: str = "locked"  # locked | in_progress | unlocked
    created_at: dt.datetime = Field(default_factory=utcnow)
    unlocked_at: dt.datetime | None = None


class AchievementProof(SQLModel, table=True):
    __tablename__ = "achievement_proof"

    id: int | None = Field(default=None, primary_key=True)
    achievement_id: int = Field(foreign_key="achievement.id", index=True)
    video_path: str | None = None  # путь к видео на диске (файл вне БД)
    thumbnail_path: str | None = None  # путь к превью на диске
    uploaded_at: dt.datetime = Field(default_factory=utcnow)
    notes: str | None = None
