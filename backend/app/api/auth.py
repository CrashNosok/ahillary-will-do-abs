"""Auth-роуты: register, login (подписанная HttpOnly cookie), logout, me.

Сессия — подписанная SECRET_KEY cookie (см. app.core.session); защита роутов —
через app.api.deps.require_user. register и login выставляют одинаковую сессию.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.core.security import hash_password, verify_password
from app.core.session import SESSION_COOKIE, sign
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])

# Срок жизни cookie (сек): 14 дней — личный локальный трекер, частый релогин не нужен.
_MAX_AGE = 14 * 24 * 3600


class Credentials(BaseModel):
    email: str
    password: str


def _user_out(user: User) -> dict[str, object]:
    # Явно — чтобы password_hash никогда не утёк в ответ.
    return {"id": user.id, "email": user.email}


def _set_session_cookie(response: Response, user: User) -> None:
    # Единая подписанная HttpOnly-сессия для login и register.
    response.set_cookie(
        SESSION_COOKIE,
        sign(str(user.id)),
        max_age=_MAX_AGE,
        httponly=True,
        samesite="lax",
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    creds: Credentials,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    # ponytail: select-then-insert; гонка двух дублей упрётся в unique-констрейнт (500).
    # Для локального однопользовательского трекера достаточно; ловить IntegrityError —
    # только если появится мультиюзер.
    if session.exec(select(User).where(User.email == creds.email)).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email уже зарегистрирован"
        )
    user = User(email=creds.email, password_hash=hash_password(creds.password))
    session.add(user)
    session.commit()
    session.refresh(user)
    _set_session_cookie(response, user)
    return _user_out(user)


@router.post("/login")
def login(
    creds: Credentials,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    user = session.exec(select(User).where(User.email == creds.email)).first()
    if user is None or not verify_password(creds.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный email или пароль"
        )
    _set_session_cookie(response, user)
    return _user_out(user)


@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(SESSION_COOKIE)
    return {"status": "logged out"}


@router.get("/me")
def me(user: CurrentUser) -> dict[str, object]:
    return _user_out(user)
