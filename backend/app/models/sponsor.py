"""Спонсор (M6·B29): самостоятельный каталог партнёров/спонсоров приложения.

Отдельная таблица без FK и без user-скоупа — глобальный справочник, как sport.
name уникален (повтор на CRUD → 409). description/url — необязательные детали,
logo_path — путь к логотипу на диске (файл вне БД, как SportMentor.photo_path).
"""

from sqlmodel import Field, SQLModel


class Sponsor(SQLModel, table=True):
    __tablename__ = "sponsor"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)  # уникально, повтор → 409
    description: str | None = None  # короткое описание спонсора
    url: str | None = None  # ссылка на сайт спонсора
    logo_path: str | None = None  # путь к логотипу на диске (файл вне БД)
