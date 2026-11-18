from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.auth.deps import get_optional_user
from app.modules.auth.models import User
from app.modules.checker import service as checker_service


def get_solved_ids(
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> set[int]:
    """Problem ids the current user has solved (score 1.0 at least once)."""
    return checker_service.solved_problem_ids(db, user.id) if user is not None else set()
