from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.auth.deps import get_current_user
from app.modules.auth.models import User
from app.modules.stats import service
from app.modules.stats.schemas import StatsOut

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/me", response_model=StatsOut)
def my_stats(
    lang: Literal["kk", "ru", "en"] = Query("kk"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Average score per tag (bar/radar charts) and the spaced "retry later" list."""
    return {"tags": service.tag_stats(db, user.id), "retry": service.retry_list(db, user.id, lang)}
