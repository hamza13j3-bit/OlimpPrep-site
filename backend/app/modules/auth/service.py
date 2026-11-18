from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.modules.auth.models import ROLE_ADMIN, ROLE_USER, User
from app.modules.auth.schemas import ProfileUpdate, RegisterIn


class AuthError(Exception):
    """Base class; routers translate these to HTTP errors."""


class EmailTaken(AuthError):
    pass


class BadCredentials(AuthError):
    pass


class UserBlocked(AuthError):
    pass


def get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def register(db: Session, data: RegisterIn) -> User:
    is_first = db.scalar(select(func.count()).select_from(User)) == 0
    is_env_admin = bool(settings.admin_email) and data.email == settings.admin_email.strip().lower()
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        name=data.name,
        school_group=data.school_group,
        language=data.language,
        role=ROLE_ADMIN if (is_first or is_env_admin) else ROLE_USER,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise EmailTaken from None
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    # Same error for unknown email and wrong password.
    if user is None or not verify_password(password, user.password_hash):
        raise BadCredentials
    if user.is_blocked:
        raise UserBlocked
    return user


def update_profile(db: Session, user: User, data: ProfileUpdate) -> User:
    for field, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(user, field, value)
    db.commit()
    return user


def set_blocked(db: Session, target: User, blocked: bool) -> User:
    target.is_blocked = blocked
    db.commit()
    return target


def promote(db: Session, target: User) -> User:
    target.role = ROLE_ADMIN
    db.commit()
    return target
