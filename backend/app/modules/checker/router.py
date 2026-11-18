from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.auth.deps import get_active_user, get_current_user, get_optional_user
from app.modules.auth.models import ROLE_ADMIN, User
from app.modules.checker import service
from app.modules.checker.models import STATE_DONE
from app.modules.checker.schemas import (
    ProblemSummary,
    SubmissionListItem,
    SubmissionResult,
    SubmitIn,
    SubmittedOut,
)

router = APIRouter(prefix="/submissions", tags=["checker"])


def get_queue(request: Request):
    return request.app.state.check_queue


@router.post("", response_model=SubmittedOut, status_code=status.HTTP_202_ACCEPTED)
def submit(
    data: SubmitIn,
    user: User = Depends(get_active_user),  # blocked users cannot submit
    db: Session = Depends(get_db),
    queue=Depends(get_queue),
):
    try:
        sub = service.create_submission(db, user, data.problem_id, data.language, data.code)
    except service.ProblemNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Problem not found") from None
    except service.TooManyPending:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many submissions in progress") from None
    queue.submit(sub.id)
    return {"id": sub.id}


@router.get("", response_model=list[SubmissionListItem])
def my_submissions(
    problem_id: int | None = None,
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service.list_user_submissions(db, user.id, problem_id, limit)


@router.get("/problem/{problem_id}/summary", response_model=ProblemSummary)
def problem_summary(
    problem_id: int, user: User | None = Depends(get_optional_user), db: Session = Depends(get_db)
):
    """Public solved count; best_score is 0 for anonymous visitors."""
    return {
        "solved_count": service.solved_count(db, problem_id),
        "best_score": service.best_score(db, user.id, problem_id) if user else 0.0,
    }


@router.get("/{submission_id}", response_model=SubmissionResult, responses={202: {"model": SubmittedOut}})
def get_result(
    submission_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    sub = service.get_submission(db, submission_id)
    if sub is None or (sub.user_id != user.id and user.role != ROLE_ADMIN):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found")
    if sub.state != STATE_DONE:  # still being checked: poll again
        return JSONResponse({"id": sub.id}, status_code=status.HTTP_202_ACCEPTED)
    return sub
