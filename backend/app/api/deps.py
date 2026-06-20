"""FastAPI-зависимости auth: текущий пользователь из подписанной cookie.

require_user — guard для защищённых роутов: нет/битая cookie или нет такого юзера → 401.
Будущие роуты подключают защиту через `user: CurrentUser`.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session

from app.core.db import get_session
from app.core.session import SESSION_COOKIE, unsign
from app.models.user import User


def require_user(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> User:
    """Требует валидную сессию. Иначе 401."""
    raw = request.cookies.get(SESSION_COOKIE)
    user_id = unsign(raw) if raw else None
    user = session.get(User, int(user_id)) if user_id and user_id.isdigit() else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Не авторизован")
    return user


CurrentUser = Annotated[User, Depends(require_user)]
