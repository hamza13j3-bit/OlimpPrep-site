from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.admin import audit
from app.modules.auth.deps import get_active_user, get_current_user, get_optional_user, require_admin
from app.modules.auth.models import ROLE_ADMIN, User
from app.modules.problems import service
from app.modules.problems.deps import get_solved_ids
from app.modules.problems.schemas import (
    HintRevealed,
    IdeaNoteIn,
    IdeaNoteModerationOut,
    IdeaNoteOut,
    ProblemAdminOut,
    ProblemIn,
    ProblemPublic,
    TagIn,
    TagOut,
)

router = APIRouter(tags=["problems"])


def _or_404(db: Session, problem_id: int):
    p = service.get_problem(db, problem_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Problem not found")
    return p


@router.get("/tags", response_model=list[TagOut])
def tags(db: Session = Depends(get_db)):
    return service.list_tags(db)


@router.post("/tags", response_model=TagOut, status_code=status.HTTP_201_CREATED)
def add_tag(data: TagIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        tag = service.create_tag(db, data.slug)
    except service.TagExists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Tag already exists") from None
    audit.record(db, admin, "tag.create", "tag", tag.id, data.slug)
    return tag


@router.post("/problems", response_model=ProblemAdminOut, status_code=status.HTTP_201_CREATED)
def create_problem(data: ProblemIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        p = service.create_problem(db, data)
    except service.UnknownTags as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    audit.record(db, admin, "problem.create", "problem", p.id)
    return service.admin_view(p)


@router.get("/problems/{problem_id}", response_model=ProblemPublic)
def read_problem(
    problem_id: int,
    lang: Literal["kk", "ru", "en"] = Query("kk"),
    user: User | None = Depends(get_optional_user),
    solved_ids: set[int] = Depends(get_solved_ids),
    db: Session = Depends(get_db),
):
    p = _or_404(db, problem_id)
    is_admin = user is not None and user.role == ROLE_ADMIN
    return service.public_view(p, lang, solved=problem_id in solved_ids, is_admin=is_admin)


@router.get("/problems/{problem_id}/hints", response_model=list[HintRevealed])
def my_hints(
    problem_id: int,
    lang: Literal["kk", "ru", "en"] = Query("kk"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Hints this user has already opened (so the page can show them again)."""
    return service.revealed_hints(db, user.id, _or_404(db, problem_id), lang)


@router.post("/problems/{problem_id}/hints/{level}", response_model=HintRevealed)
def open_hint(
    problem_id: int,
    level: int = Path(ge=1, le=3),
    lang: Literal["kk", "ru", "en"] = Query("kk"),
    user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    """Open a hint. Opening it is recorded: the deepest level used lowers the rated score S."""
    p = _or_404(db, problem_id)
    try:
        text = service.reveal_hint(db, user.id, p, level, lang)
    except service.HintNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such hint") from None
    return {"level": level, "text": text}


@router.get("/problems/{problem_id}/note", response_model=IdeaNoteOut | None)
def my_note(problem_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The caller's own plan for this problem (null = the editor is still locked). Never anyone else's."""
    _or_404(db, problem_id)
    return service.get_note(db, user.id, problem_id)


@router.put("/problems/{problem_id}/note", response_model=IdeaNoteOut)
def save_my_note(
    problem_id: int,
    data: IdeaNoteIn,
    user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    """Write the plan (>= 30 words, whole checklist ticked); this unlocks the editor server-side."""
    _or_404(db, problem_id)
    return service.save_note(db, user.id, problem_id, data)


@router.get("/problems/{problem_id}/notes", response_model=list[IdeaNoteModerationOut])
def notes_for_moderation(
    problem_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)
):
    """Admin only, read-only: plans written for this problem (moderation)."""
    _or_404(db, problem_id)
    return service.notes_for_moderation(db, problem_id)


@router.get("/problems/{problem_id}/admin", response_model=ProblemAdminOut)
def read_problem_admin(
    problem_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)
):
    return service.admin_view(_or_404(db, problem_id))


@router.put("/problems/{problem_id}", response_model=ProblemAdminOut)
def update_problem(
    problem_id: int,
    data: ProblemIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    p = _or_404(db, problem_id)
    try:
        p = service.update_problem(db, p, data)
    except service.UnknownTags as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    audit.record(db, admin, "problem.update", "problem", p.id)
    return service.admin_view(p)


@router.delete("/problems/{problem_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_problem(problem_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    service.delete_problem(db, _or_404(db, problem_id))
    audit.record(db, admin, "problem.delete", "problem", problem_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
