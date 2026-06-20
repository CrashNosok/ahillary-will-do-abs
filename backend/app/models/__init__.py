"""SQLModel-модели. Импорт здесь регистрирует таблицы в SQLModel.metadata."""

from app.models.user import User

__all__ = ["User"]
