"""Password hashing, server-side sessions and the auth dependencies (spec 1.1, DECISIONS #3)."""

import secrets
from datetime import UTC, datetime
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, Request, Response
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from api import config
from api.db import get_db
from api.errors import ApiError, forbidden, unauthenticated
from api.models import Session as UserSession
from api.models import User

COOKIE = "session"
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def login(db: Session, response: Response, email: str, password: str) -> User:
    user = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
    if not user or not verify_password(user.password_hash, password) or not user.active:
        raise ApiError(401, "unauthenticated", "Wrong email or password.")
    token = secrets.token_urlsafe(32)
    db.add(UserSession(id=token, user_id=user.id, expires_at=datetime.now(UTC) + config.SESSION_TTL))
    response.set_cookie(COOKIE, token, max_age=int(config.SESSION_TTL.total_seconds()), httponly=True,
                        samesite="lax", secure=config.COOKIE_SECURE)
    return user


def logout(db: Session, response: Response, token: str | None) -> None:
    if token:
        db.execute(delete(UserSession).where(UserSession.id == token))
    response.delete_cookie(COOKIE)


def user_for_token(db: Session, token: str | None) -> User | None:
    """The active user owning an unexpired session, or None. Also used by the WebSocket handshake."""
    if not token:
        return None
    return db.scalar(
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(UserSession.id == token, UserSession.expires_at > func.now(), User.active)
    )


DB = Annotated[Session, Depends(get_db)]


def current_user(request: Request, db: DB) -> User:
    user = user_for_token(db, request.cookies.get(COOKIE))
    if not user:
        raise unauthenticated()
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise forbidden("Admins only.", code="admin_required")
    return user


Admin = Annotated[User, Depends(require_admin)]
