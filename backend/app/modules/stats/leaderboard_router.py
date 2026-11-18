from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.auth.deps import get_optional_user
from app.modules.auth.models import User
from app.modules.problems import service as problems_service
from app.modules.stats import leaderboard
from app.modules.stats.leaderboard_schemas import LeaderPage

router = APIRouter(prefix="/leaderboards", tags=["leaderboards"])

PageQ = Query(1, ge=1, le=100_000)


def _me(user: User | None) -> int | None:
    return user.id if user is not None and not user.is_blocked else None


@router.get("/global", response_model=LeaderPage)
def global_board(page: int = PageQ, user: User | None = Depends(get_optional_user), db: Session = Depends(get_db)):
    return leaderboard.page(db, "global", None, page, _me(user))


@router.get("/duel", response_model=LeaderPage)
def duel_board(page: int = PageQ, user: User | None = Depends(get_optional_user), db: Session = Depends(get_db)):
    return leaderboard.page(db, "duel", None, page, _me(user))


@router.get("/tag/{slug}", response_model=LeaderPage)
def tag_board(
    slug: str, page: int = PageQ, user: User | None = Depends(get_optional_user), db: Session = Depends(get_db)
):
    if slug not in {t.slug for t in problems_service.list_tags(db)}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown tag")
    return leaderboard.page(db, "tag", slug, page, _me(user))
