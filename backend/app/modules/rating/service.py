import threading

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.problems import service as problems_service
from app.modules.rating import elo
from app.modules.rating.models import (
    SCOPE_GLOBAL,
    PlayerRating,
    ProblemRating,
    RatingEvent,
    TagRating,
    tag_scope,
)

# One rating write at a time inside this process (checker workers are threads).
_lock = threading.Lock()


def apply_result(db: Session, user_id: int, submission_id: int, problem_id: int, score: float) -> bool:
    """Rate a checked submission. Returns True if ratings changed.

    A submission is rated only if it is the user's first on this problem or beats their
    previous best score on it - re-submitting the same or a worse result changes nothing,
    and a solved problem (best 1.0) is never rated again. Idempotent per submission.
    """
    with _lock:
        try:
            changed = _apply(db, user_id, submission_id, problem_id, score)
            db.commit()
            return changed
        except Exception:
            db.rollback()
            raise


def _apply(db: Session, user_id: int, submission_id: int, problem_id: int, score: float) -> bool:
    problem = problems_service.get_problem(db, problem_id)
    if problem is None:
        return False
    already = db.scalar(
        select(RatingEvent.id).where(
            RatingEvent.submission_id == submission_id, RatingEvent.scope == SCOPE_GLOBAL
        )
    )
    if already is not None:
        return False
    best_prev = db.scalar(
        select(func.max(RatingEvent.raw_score)).where(
            RatingEvent.user_id == user_id,
            RatingEvent.problem_id == problem_id,
            RatingEvent.scope == SCOPE_GLOBAL,
        )
    )
    if best_prev is not None and score <= best_prev + 1e-9:
        return False

    hint_level = problems_service.max_hint_level(db, user_id, problem_id)
    s = elo.effective_score(score, hint_level)

    pr = db.get(ProblemRating, problem_id)
    if pr is None:
        pr = ProblemRating(problem_id=problem_id, rating=float(problem.rating))
        db.add(pr)
    elif round(pr.rating) != problem.rating:
        pr.rating = float(problem.rating)  # an admin edited the rating: restart from it

    player = db.get(PlayerRating, user_id)
    if player is None:
        player = PlayerRating(user_id=user_id, rating=elo.START_RATING, attempts=0)
        db.add(player)

    def event(scope: str, e: float, k: float, old: float, new: float) -> None:
        db.add(
            RatingEvent(
                user_id=user_id, submission_id=submission_id, problem_id=problem_id, scope=scope,
                raw_score=score, effective_score=s, hint_level=hint_level,
                expected=e, k=k, old_rating=old, new_rating=new,
            )
        )

    r_problem = pr.rating
    e_global = elo.expected(player.rating, r_problem)
    k_global = elo.k_player(player.attempts)
    old_player = player.rating
    new_player = elo.apply_delta(old_player, k_global * (s - e_global))
    event(SCOPE_GLOBAL, e_global, k_global, old_player, new_player)

    for slug in [t.slug for t in problem.tags]:
        tr = db.get(TagRating, (user_id, slug))
        if tr is None:
            tr = TagRating(user_id=user_id, tag=slug, rating=elo.START_RATING, attempts=0)
            db.add(tr)
        e_t = elo.expected(tr.rating, r_problem)
        k_t = elo.k_player(tr.attempts)
        new_t = elo.apply_delta(tr.rating, k_t * (s - e_t))
        event(tag_scope(slug), e_t, k_t, tr.rating, new_t)
        tr.rating = new_t
        tr.attempts += 1

    # The problem plays the mirror game against the player's overall rating.
    new_problem = elo.apply_delta(r_problem, elo.problem_delta(old_player, r_problem, s))
    pr.rating = new_problem
    problems_service.set_rating(db, problem_id, round(new_problem))

    player.rating = new_player
    player.attempts += 1
    return True


# ---- reads --------------------------------------------------------------------


def get_player(db: Session, user_id: int) -> dict:
    p = db.get(PlayerRating, user_id)
    tags = db.scalars(select(TagRating).where(TagRating.user_id == user_id).order_by(TagRating.tag))
    return {
        "rating": p.rating if p else elo.START_RATING,
        "attempts": p.attempts if p else 0,
        "tags": [{"tag": t.tag, "rating": t.rating, "attempts": t.attempts} for t in tags],
    }


def history(db: Session, user_id: int, tag: str | None, limit: int) -> list[RatingEvent]:
    scope = tag_scope(tag) if tag else SCOPE_GLOBAL
    rows = db.scalars(
        select(RatingEvent)
        .where(RatingEvent.user_id == user_id, RatingEvent.scope == scope)
        .order_by(RatingEvent.id.desc())
        .limit(limit)
    )
    return list(reversed(list(rows)))  # oldest first, ready for a chart


def set_rating_manually(db: Session, user_id: int, tag: str | None, new_rating: float) -> float:
    """Admin correction of the overall (tag=None) or a per-tag rating. Returns the old value.

    Writes no rating_history row (those belong to submissions). A row created here has
    attempts = 0, so the player stays off the leaderboards until they make a rated attempt.
    """
    with _lock:
        try:
            if tag is None:
                row = db.get(PlayerRating, user_id)
                if row is None:
                    row = PlayerRating(user_id=user_id, rating=elo.START_RATING, attempts=0)
                    db.add(row)
            else:
                row = db.get(TagRating, (user_id, tag))
                if row is None:
                    row = TagRating(user_id=user_id, tag=tag, rating=elo.START_RATING, attempts=0)
                    db.add(row)
            old = float(row.rating)
            row.rating = new_rating
            db.commit()
            return old
        except Exception:
            db.rollback()
            raise
