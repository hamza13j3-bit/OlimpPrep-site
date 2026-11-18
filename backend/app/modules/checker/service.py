import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import case, distinct, false, func, select
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.checker import runner
from app.modules.checker.models import STATE_DONE, STATE_QUEUED, STATE_RUNNING, Submission
from app.modules.problems import service as problems_service
from app.modules.rating import service as rating_service

log = logging.getLogger(__name__)

MAX_PENDING_PER_USER = 3


class CheckerError(Exception):
    pass


class ProblemNotFound(CheckerError):
    pass


class TooManyPending(CheckerError):
    pass


@dataclass(frozen=True)
class CheckedSubmission:
    """What listeners (e.g. the duel module) learn about a finished check."""

    user_id: int
    problem_id: int
    submission_id: int
    duel_match_id: int | None
    created_at: datetime
    score: float
    solved: bool
    tests_total: int


Listener = Callable[[Session, CheckedSubmission], None]
_listeners: list[Listener] = []


def add_listener(fn: Listener) -> None:
    """Register a callback run after every checked submission (idempotent)."""
    if fn not in _listeners:
        _listeners.append(fn)


def pending_duel_count(db: Session, match_id: int) -> int:
    return db.scalar(
        select(func.count()).select_from(Submission).where(
            Submission.duel_match_id == match_id, Submission.state != STATE_DONE
        )
    ) or 0


def create_submission(
    db: Session,
    user: User,
    problem_id: int,
    language: str,
    code: str,
    duel_match_id: int | None = None,
) -> Submission:
    if problems_service.get_problem(db, problem_id) is None:
        raise ProblemNotFound
    pending = db.scalar(
        select(func.count()).select_from(Submission).where(
            Submission.user_id == user.id, Submission.state != STATE_DONE
        )
    )
    if pending >= MAX_PENDING_PER_USER:
        raise TooManyPending
    sub = Submission(
        user_id=user.id, problem_id=problem_id, language=language, code=code, duel_match_id=duel_match_id
    )
    db.add(sub)
    db.commit()
    return sub


def build_spec(problem) -> runner.ProblemSpec:
    return runner.ProblemSpec(
        time_limit_ms=problem.time_limit_ms,
        memory_limit_mb=problem.memory_limit_mb,
        subtasks=tuple(
            runner.SubtaskSpec(
                points=st.points,
                tests=tuple(runner.CaseSpec(t.input_data, t.output_data) for t in st.tests),
            )
            for st in problem.subtasks
        ),
    )


def process_submission(db: Session, submission_id: int) -> None:
    """Check one submission and store the result. Safe to call twice (second call is a no-op)."""
    sub = db.get(Submission, submission_id)
    if sub is None or sub.state == STATE_DONE:
        return
    sub.state = STATE_RUNNING
    db.commit()

    problem = problems_service.get_problem(db, sub.problem_id)
    result = runner.CheckResult(0, 0, 0.0, False)
    if problem is not None:
        spec = build_spec(problem)
        try:
            result = runner.check(sub.language, sub.code, spec)
        except Exception:  # never leak internals; an internal failure = nothing passed
            log.exception("checker crashed on submission %s", submission_id)
            result = runner.CheckResult(0, sum(len(s.tests) for s in spec.subtasks), 0.0, False)

    sub.tests_passed = result.tests_passed
    sub.tests_total = result.tests_total
    sub.score = result.score
    sub.solved = result.solved
    sub.state = STATE_DONE
    sub.finished_at = datetime.now(timezone.utc)
    db.commit()

    if result.tests_total > 0 and sub.duel_match_id is None:  # duels do not touch training ratings
        try:
            rating_service.apply_result(db, sub.user_id, sub.id, sub.problem_id, sub.score)
        except Exception:  # the checked result is already saved; never lose it over rating
            log.exception("rating update failed for submission %s", submission_id)

    checked = CheckedSubmission(
        user_id=sub.user_id, problem_id=sub.problem_id, submission_id=sub.id,
        duel_match_id=sub.duel_match_id, created_at=sub.created_at, score=sub.score,
        solved=sub.solved, tests_total=result.tests_total,
    )
    for listener in list(_listeners):
        try:
            listener(db, checked)
        except Exception:  # a listener must never break checking
            db.rollback()
            log.exception("checker listener %r failed for submission %s", listener, submission_id)


def unfinished_ids(db: Session) -> list[int]:
    return list(db.scalars(select(Submission.id).where(Submission.state != STATE_DONE).order_by(Submission.id)))


def reset_interrupted(db: Session) -> None:
    """After a crash/restart, jobs stuck in `running` go back to the queue."""
    for sub in db.scalars(select(Submission).where(Submission.state == STATE_RUNNING)):
        sub.state = STATE_QUEUED
    db.commit()


def get_submission(db: Session, submission_id: int) -> Submission | None:
    return db.get(Submission, submission_id)


def list_user_submissions(db: Session, user_id: int, problem_id: int | None, limit: int) -> list[Submission]:
    q = select(Submission).where(Submission.user_id == user_id, Submission.state == STATE_DONE)
    if problem_id is not None:
        q = q.where(Submission.problem_id == problem_id)
    return list(db.scalars(q.order_by(Submission.id.desc()).limit(limit)))


# ---- queries other modules use (archive, rating, duel) ------------------------


def solved_problem_ids(db: Session, user_id: int) -> set[int]:
    """Problems with score 1.0 reached at least once."""
    return set(
        db.scalars(
            select(Submission.problem_id)
            .where(Submission.user_id == user_id, Submission.solved.is_(True))
            .distinct()
        )
    )


def solved_counts_subquery():
    """(problem_id, cnt): distinct users who solved each problem. For one-query listings."""
    return (
        select(Submission.problem_id.label("problem_id"), func.count(distinct(Submission.user_id)).label("cnt"))
        .where(Submission.solved.is_(True))
        .group_by(Submission.problem_id)
        .subquery()
    )


def user_status_subquery(user_id: int | None):
    """(problem_id, attempts, solved): the user's finished submissions per problem.
    solved = 1 if score 1.0 was reached at least once. No rows for anonymous users."""
    q = select(
        Submission.problem_id.label("problem_id"),
        func.count().label("attempts"),
        func.max(case((Submission.solved.is_(True), 1), else_=0)).label("solved"),
    ).where(Submission.state == STATE_DONE)
    q = q.where(Submission.user_id == user_id) if user_id is not None else q.where(false())
    return q.group_by(Submission.problem_id).subquery()


def solved_count(db: Session, problem_id: int) -> int:
    return db.scalar(
        select(func.count(distinct(Submission.user_id))).where(
            Submission.problem_id == problem_id, Submission.solved.is_(True)
        )
    ) or 0


def best_score(db: Session, user_id: int, problem_id: int) -> float:
    return db.scalar(
        select(func.max(Submission.score)).where(
            Submission.user_id == user_id,
            Submission.problem_id == problem_id,
            Submission.state == STATE_DONE,
        )
    ) or 0.0


def best_results(db: Session, user_id: int) -> dict[int, tuple[float, bool]]:
    """problem_id -> (best score, solved at least once) over the user's finished submissions."""
    rows = db.execute(
        select(
            Submission.problem_id,
            func.max(Submission.score),
            func.max(case((Submission.solved.is_(True), 1), else_=0)),
        )
        .where(Submission.user_id == user_id, Submission.state == STATE_DONE)
        .group_by(Submission.problem_id)
    )
    return {pid: (float(best or 0.0), bool(solved)) for pid, best, solved in rows}


def solved_per_user_subquery(tag_slug: str | None = None):
    """(user_id, cnt): distinct problems each user solved, optionally only those with a tag."""
    from app.modules.problems.models import Tag, problem_tags

    q = select(Submission.user_id.label("user_id"), func.count(distinct(Submission.problem_id)).label("cnt")).where(
        Submission.solved.is_(True)
    )
    if tag_slug is not None:
        q = (
            q.join(problem_tags, problem_tags.c.problem_id == Submission.problem_id)
            .join(Tag, Tag.id == problem_tags.c.tag_id)
            .where(Tag.slug == tag_slug)
        )
    return q.group_by(Submission.user_id).subquery()


def submissions_per_day(db: Session, since: datetime) -> dict[str, int]:
    """'YYYY-MM-DD' (UTC) -> number of submissions created on or after `since`."""
    rows = db.execute(
        select(func.date(Submission.created_at), func.count()).where(Submission.created_at >= since).group_by(
            func.date(Submission.created_at)
        )
    )
    return {day: n for day, n in rows}


def solved_counts_all(db: Session) -> list[tuple[int, int]]:
    """(problem_id, distinct solvers) for EVERY problem, zero included."""
    from app.modules.problems.models import Problem

    sub = solved_counts_subquery()
    rows = db.execute(
        select(Problem.id, func.coalesce(sub.c.cnt, 0)).outerjoin(sub, sub.c.problem_id == Problem.id)
    )
    return [(pid, int(n)) for pid, n in rows]
