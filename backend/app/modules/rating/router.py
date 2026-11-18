from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.auth.deps import get_current_user
from app.modules.auth.models import User
from app.modules.rating import service
from app.modules.rating.schemas import HistoryPoint, RatingOut

router = APIRouter(prefix="/rating", tags=["rating"])


@router.get("/me", response_model=RatingOut)
def my_rating(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.get_player(db, user.id)


@router.get("/me/history", response_model=list[HistoryPoint])
def my_history(
    tag: str | None = Query(None, max_length=30),
    limit: int = Query(500, ge=1, le=2000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Global rating history, or one tag's history with ?tag=dp. Oldest first."""
    return service.history(db, user.id, tag, limit)
