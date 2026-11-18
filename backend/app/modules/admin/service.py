import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.admin.models import AuditLog
from app.modules.auth.models import ROLE_ADMIN, User
from app.modules.checker import service as checker_service
from app.modules.checker.models import Submission
from app.modules.duel import service as duel_service
from app.modules.problems import service as problems_service
from app.modules.rating import service as rating_service
from app.modules.rating.models import PlayerRating

PAGE_SIZE = 50
DAYS = 30
TOP = 10


class AdminError(Exception):
    pass


class UnknownTag(AdminError):
    pass


# ---- users --------------------------------------------------------------------


def list_users(db: Session, q: str | None, page: int) -> dict:
    """Users table. Search is case-insensitive over name and e-mail (done in Python so that
    Cyrillic works: SQLite lower()/LIKE only fold ASCII)."""
    base = select(User, PlayerRating.rating).outerjoin(PlayerRating, PlayerRating.user_id == User.id)
    needle = (q or "").strip().casefold()
    if needle:
        ids = [
            uid
            for uid, name, email in db.execute(select(User.id, User.name, User.email).order_by(User.id))
            if needle in name.casefold() or needle in email.casefold()
        ]
        total = len(ids)
        ids = ids[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]
        rows = db.execute(base.where(User.id.in_(ids)).order_by(User.id)).all() if ids else []
    else:
        total = db.scalar(select(func.count()).select_from(User)) or 0
        rows = db.execute(base.order_by(User.id).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)).all()
    items = [
        {
            "id": u.id, "email": u.email, "name": u.name, "school_group": u.school_group,
            "role": u.role, "is_blocked": u.is_blocked, "created_at": u.created_at, "rating": rating,
        }
        for u, rating in rows
    ]
    return {"items": items, "total": total, "page": page, "page_size": PAGE_SIZE}


def user_row(db: Session, user_id: int) -> dict:
    u, rating = db.execute(
        select(User, PlayerRating.rating)
        .outerjoin(PlayerRating, PlayerRating.user_id == User.id)
        .where(User.id == user_id)
    ).one()
    return {
        "id": u.id, "email": u.email, "name": u.name, "school_group": u.school_group,
        "role": u.role, "is_blocked": u.is_blocked, "created_at": u.created_at, "rating": rating,
    }


# ---- dashboard numbers ------------------------------------------------------------


def stats(db: Session, lang: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    today = now.date()
    start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc) - timedelta(days=DAYS - 1)
    per_day = checker_service.submissions_per_day(db, start)
    days = [(start + timedelta(days=i)).date().isoformat() for i in range(DAYS)]

    solved = sorted(checker_service.solved_counts_all(db), key=lambda x: x[0])  # by problem id
    most = sorted(solved, key=lambda x: (-x[1], x[0]))[:TOP]
    least = sorted(solved, key=lambda x: (x[1], x[0]))[:TOP]
    titles = problems_service.titles_for(db, sorted({pid for pid, _ in most + least}), lang)

    def rows(pairs):
        return [{"problem_id": pid, "title": titles.get(pid, str(pid)), "solved": n} for pid, n in pairs]

    return {
        "users_total": db.scalar(select(func.count()).select_from(User)) or 0,
        "users_blocked": db.scalar(select(func.count()).select_from(User).where(User.is_blocked.is_(True))) or 0,
        "admins": db.scalar(select(func.count()).select_from(User).where(User.role == ROLE_ADMIN)) or 0,
        "submissions_total": db.scalar(select(func.count()).select_from(Submission)) or 0,
        "submissions_per_day": [{"day": d, "count": per_day.get(d, 0)} for d in days],
        "most_solved": rows(most),
        "least_solved": rows(least),
    }


# ---- rating correction -------------------------------------------------------------


def correct_rating(db: Session, target: User, scope: str, tag: str | None, new_rating: float) -> tuple[float, float]:
    if scope == "tag":
        if tag not in {t.slug for t in problems_service.list_tags(db)}:
            raise UnknownTag(tag)
        old = rating_service.set_rating_manually(db, target.id, tag, new_rating)
    elif scope == "duel":
        old = duel_service.set_rating_manually(db, target.id, new_rating)
    else:
        old = rating_service.set_rating_manually(db, target.id, None, new_rating)
    return old, new_rating


# ---- audit log -----------------------------------------------------------------------


def audit_page(db: Session, page: int) -> dict:
    total = db.scalar(select(func.count()).select_from(AuditLog)) or 0
    rows = db.execute(
        select(AuditLog, User.name)
        .join(User, User.id == AuditLog.admin_id)
        .order_by(AuditLog.id.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
    ).all()
    items = [
        {
            "id": a.id, "admin_id": a.admin_id, "admin_name": name, "action": a.action,
            "target_type": a.target_type, "target_id": a.target_id, "target_label": a.target_label,
            "details": json.loads(a.details or "{}"), "created_at": a.created_at,
        }
        for a, name in rows
    ]
    return {"items": items, "total": total, "page": page, "page_size": PAGE_SIZE}
