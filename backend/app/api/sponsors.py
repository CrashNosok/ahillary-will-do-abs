"""CRUD спонсоров (M6·B29).

Самостоятельный каталог sponsor(name, description, url, logo_path) с полным CRUD.
name уникален — повтор отдаёт 409, неизвестный id — 404. Все роуты под сессией
(CurrentUser) — приложение однопользовательское, как и остальной каталог.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.models.sponsor import Sponsor

router = APIRouter(prefix="/sponsors", tags=["sponsors"])

SessionDep = Annotated[Session, Depends(get_session)]


class SponsorCreate(BaseModel):
    name: str
    description: str | None = None
    url: str | None = None
    logo_path: str | None = None


class SponsorUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    url: str | None = None
    logo_path: str | None = None


def _get_or_404(session: Session, sponsor_id: int) -> Sponsor:
    sponsor = session.get(Sponsor, sponsor_id)
    if sponsor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Спонсор не найден")
    return sponsor


def _commit_unique(session: Session, sponsor: Sponsor) -> Sponsor:
    """Сохраняет и переводит конфликт уникального name в 409 вместо 500."""
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Спонсор с таким именем уже есть"
        ) from exc
    session.refresh(sponsor)
    return sponsor


@router.post("", status_code=status.HTTP_201_CREATED)
def create_sponsor(payload: SponsorCreate, session: SessionDep, _: CurrentUser) -> Sponsor:
    sponsor = Sponsor(**payload.model_dump())
    session.add(sponsor)
    return _commit_unique(session, sponsor)


@router.get("")
def list_sponsors(session: SessionDep, _: CurrentUser) -> list[Sponsor]:
    """Каталог спонсоров по имени."""
    return session.exec(select(Sponsor).order_by(Sponsor.name)).all()


@router.get("/{sponsor_id}")
def get_sponsor(sponsor_id: int, session: SessionDep, _: CurrentUser) -> Sponsor:
    return _get_or_404(session, sponsor_id)


@router.patch("/{sponsor_id}")
def update_sponsor(
    sponsor_id: int, payload: SponsorUpdate, session: SessionDep, _: CurrentUser
) -> Sponsor:
    sponsor = _get_or_404(session, sponsor_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(sponsor, key, value)
    session.add(sponsor)
    return _commit_unique(session, sponsor)


@router.delete("/{sponsor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sponsor(sponsor_id: int, session: SessionDep, _: CurrentUser) -> None:
    sponsor = _get_or_404(session, sponsor_id)
    session.delete(sponsor)
    session.commit()
