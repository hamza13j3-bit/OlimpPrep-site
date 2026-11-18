from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.checker import service as checker_service
from app.modules.checker.service import CheckedSubmission
from app.modules.problems import service as problems_service
from app.modules.stats.models import RetrySchedule

RETRY_DAYS = (1, 3, 7, 14)
EPS = 1e-9


def _utc(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; everything here is UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---- retry-later schedule -------------------------------------------------------


def record_attempt(
    db: Session, user_id: int, problem_id: int, best_score: float, now: datetime, *, schedule: bool = True
) -> None:
    """Update the retry schedule after a finished submission. The caller commits.

    - best score reached 1.0: the problem leaves the list for good;
    - first unsolved attempt: it reappears after RETRY_DAYS[0] = 1 day;
    - an attempt made when the problem was DUE moves it one stage on (3, 7, 14 days; 14 repeats);
    - an attempt made before it was due changes nothing (no way to rush the schedule).
    `schedule=False` (duel submissions) only removes solved problems, it never adds any.
    """
    row = db.get(RetrySchedule, (user_id, problem_id))
    if best_score >= 1.0 - EPS:
        if row is not None:
            db.delete(row)
        return
    if not schedule:
        return
    if row is None:
        db.add(
            RetrySchedule(
                user_id=user_id, problem_id=problem_id, stage=0,
                next_due_at=now + timedelta(days=RETRY_DAYS[0]), updated_at=now,
            )
        )
        return
    if now >= _utc(row.next_due_at):
        row.stage = min(row.stage + 1, len(RETRY_DAYS) - 1)
        row.next_due_at = now + timedelta(days=RETRY_DAYS[row.stage])
        row.updated_at = now


def on_checked(db: Session, c: CheckedSubmission) -> None:
    """Checker listener (registered in main)."""
    if c.tests_total <= 0:
        return
    best, _solved = checker_service.best_results(db, c.user_id).get(c.problem_id, (c.score, c.solved))
    record_attempt(
        db, c.user_id, c.problem_id, best, datetime.now(timezone.utc), schedule=c.duel_match_id is None
    )
    db.commit()


def register() -> None:
    checker_service.add_listener(on_checked)


# ---- reads ------------------------------------------------------------------------


def tag_stats(db: Session, user_id: int) -> list[dict]:
    """Average best score per tag over the problems the user attempted.

    A problem with hidden tags that the user has not solved is left out, so the chart can
    never reveal what the statement page hides. Every tag appears (0 problems -> avg 0)
    so the radar chart keeps all its axes.
    """
    results = checker_service.best_results(db, user_id)
    info = problems_service.tag_info(db, list(results))
    acc: dict[str, list[float]] = {t.slug: [] for t in problems_service.list_tags(db)}
    solved: dict[str, int] = {slug: 0 for slug in acc}
    for pid, (best, was_solved) in results.items():
        slugs, hide = info.get(pid, ([], False))
        if hide and not was_solved:
            continue
        for slug in slugs:
            acc.setdefault(slug, []).append(best)
            solved[slug] = solved.get(slug, 0) + (1 if best >= 1.0 - EPS else 0)
    return [
        {"tag": slug, "avg_score": (sum(v) / len(v) if v else 0.0), "attempted": len(v), "solved": solved[slug]}
        for slug, v in sorted(acc.items())
    ]


def retry_list(db: Session, user_id: int, lang: str, now: datetime | None = None) -> list[dict]:
    """Scheduled problems, the ones due now first (oldest due date first), then upcoming ones."""
    now = now or datetime.now(timezone.utc)
    rows = list(db.scalars(select(RetrySchedule).where(RetrySchedule.user_id == user_id)))
    if not rows:
        return []
    ids = [r.problem_id for r in rows]
    titles = problems_service.titles_for(db, ids, lang)
    results = checker_service.best_results(db, user_id)
    items = []
    for r in rows:
        due_at = _utc(r.next_due_at)
        items.append(
            {
                "problem_id": r.problem_id,
                "title": titles.get(r.problem_id, str(r.problem_id)),
                "best_score": results.get(r.problem_id, (0.0, False))[0],
                "stage": r.stage,
                "due": due_at <= now,
                "next_due_at": due_at.isoformat(),
                "_at": due_at,
            }
        )
    items.sort(key=lambda i: (not i["due"], i["_at"], i["problem_id"]))
    for i in items:
        del i["_at"]
    return items
