from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import decode_access_token
from app.modules.auth import service
from app.modules.auth.models import ROLE_ADMIN, User

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Authenticated user, blocked or not (use for read-only endpoints like /me)."""
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    if creds is None:
        raise unauthorized
    user_id = decode_access_token(creds.credentials)
    user = service.get_user(db, user_id) if user_id is not None else None
    if user is None:
        raise unauthorized
    return user


def get_optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User | None:
    """User if a valid token is sent, else None (public pages)."""
    if creds is None:
        return None
    user_id = decode_access_token(creds.credentials)
    return service.get_user(db, user_id) if user_id is not None else None


def get_active_user(user: User = Depends(get_current_user)) -> User:
    """Authenticated and not blocked. Use for submitting and any write action."""
    if user.is_blocked:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is blocked")
    return user


def require_admin(user: User = Depends(get_active_user)) -> User:
    if user.role != ROLE_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user
