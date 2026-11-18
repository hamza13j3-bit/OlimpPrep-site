from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import create_access_token
from app.modules.auth import service
from app.modules.auth.deps import get_active_user, get_current_user
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    LoginIn,
    ProfileUpdate,
    RegisterIn,
    TokenOut,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _token(user: User) -> TokenOut:
    return TokenOut(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    try:
        user = service.register(db, data)
    except service.EmailTaken:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from None
    return _token(user)


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    try:
        user = service.authenticate(db, data.email, data.password)
    except service.BadCredentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password") from None
    except service.UserBlocked:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is blocked") from None
    return _token(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=UserOut)
def update_me(
    data: ProfileUpdate, user: User = Depends(get_active_user), db: Session = Depends(get_db)
):
    return service.update_profile(db, user, data)
