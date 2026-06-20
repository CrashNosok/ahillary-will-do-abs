"""Auth-роуты: login (подписанная HttpOnly cookie), logout, me.

Регистрации нет — логинится единственный сид-юзер. Сессия — подписанная SECRET_KEY
cookie (см. app.core.session); защита роутов — через app.api.deps.require_user.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import CurrentUser
from app.core.db import get_session
from app.core.security import verify_password
from app.core.session import SESSION_COOKIE, sign
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])

# Срок жизни cookie (сек): 14 дней — личный локальный трекер, частый релогин не нужен.
_MAX_AGE = 14 * 24 * 3600


class LoginRequest(BaseModel):
    email: str
    password: str


def _user_out(user: User) -> dict[str, object]:
    # Явно — чтобы password_hash никогда не утёк в ответ.
    return {"id": user.id, "email": user.email}


@router.post("/login")
def login(
    creds: LoginRequest,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    user = session.exec(select(User).where(User.email == creds.email)).first()
    if user is None or not verify_password(creds.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный email или пароль"
        )
    response.set_cookie(
        SESSION_COOKIE,
        sign(str(user.id)),
        max_age=_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return _user_out(user)


@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(SESSION_COOKIE)
    return {"status": "logged out"}


@router.get("/me")
def me(user: CurrentUser) -> dict[str, object]:
    return _user_out(user)
