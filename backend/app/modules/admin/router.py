from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.admin import audit, service
from app.modules.admin.schemas import (
    AdminStats,
    AdminUserOut,
    AdminUsersPage,
    AuditPage,
    RatingCorrectionIn,
    RatingCorrectionOut,
)
from app.modules.auth import service as auth_service
from app.modules.auth.deps import require_admin
from app.modules.auth.models import ROLE_ADMIN, User
from app.modules.auth.schemas import BlockIn

# Every route below depends on require_admin (401 anonymous, 403 for users and blocked admins).
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

PageQ = Query(1, ge=1, le=100_000)


def _target(db: Session, user_id: int) -> User:
    u = auth_service.get_user(db, user_id)
    if u is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return u


@router.get("/users", response_model=AdminUsersPage)
def users(q: str | None = Query(None, max_length=100), page: int = PageQ, db: Session = Depends(get_db)):
    return service.list_users(db, q, page)


@router.patch("/users/{user_id}/block", response_model=AdminUserOut)
def block_user(user_id: int, data: BlockIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    target = _target(db, user_id)
    if target.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot block yourself")
    auth_service.set_blocked(db, target, data.blocked)
    audit.record(db, admin, "user.block" if data.blocked else "user.unblock", "user", target.id, target.email)
    return service.user_row(db, target.id)


@router.post("/users/{user_id}/promote", response_model=AdminUserOut)
def promote_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    target = _target(db, user_id)
    if target.role == ROLE_ADMIN:
        raise HTTPException(status.HTTP_409_CONFLICT, "Already an admin")
    if target.is_blocked:
        raise HTTPException(status.HTTP_409_CONFLICT, "Unblock the user first")
    auth_service.promote(db, target)
    audit.record(db, admin, "user.promote", "user", target.id, target.email)
    return service.user_row(db, target.id)


@router.post("/users/{user_id}/rating", response_model=RatingCorrectionOut)
def correct_rating(
    user_id: int,
    data: RatingCorrectionIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Manual rating correction. The reason is mandatory and is written to the audit log."""
    target = _target(db, user_id)
    try:
        old, new = service.correct_rating(db, target, data.scope, data.tag, data.rating)
    except service.UnknownTag:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown tag") from None
    audit.record(
        db, admin, "rating.adjust", "user", target.id, target.email,
        {"scope": data.scope, "tag": data.tag, "old": round(old, 2), "new": new, "reason": data.reason},
    )
    return {"old_rating": round(old, 2), "new_rating": new}


@router.get("/stats", response_model=AdminStats)
def stats(lang: Literal["kk", "ru", "en"] = "kk", db: Session = Depends(get_db)):
    return service.stats(db, lang)


@router.get("/audit", response_model=AuditPage)
def audit_log(page: int = PageQ, db: Session = Depends(get_db)):
    return service.audit_page(db, page)
