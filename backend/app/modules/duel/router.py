from typing import Callable, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.auth.deps import get_active_user, get_current_user
from app.modules.auth.models import User
from app.modules.checker import service as checker_service
from app.modules.checker.router import get_queue
from app.modules.checker.schemas import SubmitIn, SubmittedOut
from app.modules.duel import service, ws
from app.modules.duel.deps import get_session_factory

router = APIRouter(prefix="/duel", tags=["duel"])


@router.post("/queue", status_code=status.HTTP_202_ACCEPTED)
def join_queue(user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    """Enter matchmaking. The match itself is announced over the WebSocket / GET /duel/me."""
    try:
        service.join_queue(db, user.id, service.now())
    except service.AlreadyInDuel:
        raise HTTPException(status.HTTP_409_CONFLICT, "You are already in a duel") from None
    except service.AlreadyWaiting:
        raise HTTPException(status.HTTP_409_CONFLICT, "You are already waiting for an opponent") from None
    return service.state_for_user(db, user.id, service.now())


@router.delete("/queue", status_code=status.HTTP_204_NO_CONTENT)
def leave_queue(user: User = Depends(get_current_user)):
    try:
        service.leave_queue(user.id)
    except service.NotWaiting:
        raise HTTPException(status.HTTP_409_CONFLICT, "You are not waiting for an opponent") from None


@router.get("/me")
def my_state(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.state_for_user(db, user.id, service.now())


@router.get("/rating")
def my_duel_rating(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.rating_view(db, user.id)


@router.get("/matches")
def my_matches(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.history(db, user.id)


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Match not found")


@router.get("/matches/{match_id}")
def live_match(match_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return service.live_view(db, match_id, user, service.now())
    except service.MatchNotFound:
        raise _not_found() from None


@router.post(
    "/matches/{match_id}/submit", response_model=SubmittedOut, status_code=status.HTTP_202_ACCEPTED
)
def submit(
    match_id: int,
    data: SubmitIn,
    user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
    queue=Depends(get_queue),
):
    """Submit inside a duel. Poll the result with GET /submissions/{id} like any submission."""
    try:
        sub = service.submit(db, user, match_id, data.problem_id, data.language, data.code, service.now())
    except service.MatchNotFound:
        raise _not_found() from None
    except service.MatchNotActive:
        raise HTTPException(status.HTTP_409_CONFLICT, "This match is over") from None
    except service.BadProblem:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Not a problem of this match") from None
    except service.ProblemAlreadySolved:
        raise HTTPException(status.HTTP_409_CONFLICT, "You already solved this problem") from None
    except checker_service.TooManyPending:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many submissions in progress") from None
    queue.submit(sub.id)
    return {"id": sub.id}


@router.get("/matches/{match_id}/result")
def match_result(
    match_id: int,
    lang: Literal["kk", "ru", "en"] = Query("kk"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Post-match page: per player solved count, total score, penalty, and per problem details."""
    try:
        return service.result_view(db, match_id, user, lang)
    except service.MatchNotFound:
        raise _not_found() from None
    except service.MatchNotActive:
        raise HTTPException(status.HTTP_409_CONFLICT, "The match is not finished yet") from None


@router.websocket("/ws")
async def duel_socket(websocket: WebSocket, factory: Callable = Depends(get_session_factory)):
    await ws.serve(websocket, factory)
