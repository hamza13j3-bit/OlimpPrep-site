"""Leaderboards: global rating, per-tag rating, duel rating.

Order: displayed (rounded) rating desc, then solved count desc, then user id. Rank is
competition ranking on the rounded rating only: equal ratings share a rank and the next
rank skips (1, 2, 2, 4). Blocked users and players with no rated attempt / duel are left out.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.checker import service as checker_service
from app.modules.duel.models import DuelRating
from app.modules.rating.models import PlayerRating, TagRating

PAGE_SIZE = 50


def _rows(board: str, tag: str | None):
    """Subquery (user_id, name, rating, solved) of everyone who is on the board."""
    if board == "duel":
        model, eligible = DuelRating, DuelRating.games > 0
    elif board == "tag":
        model, eligible = TagRating, (TagRating.tag == tag) & (TagRating.attempts > 0)
    else:
        model, eligible = PlayerRating, PlayerRating.attempts > 0
    solved = checker_service.solved_per_user_subquery(tag if board == "tag" else None)
    return (
        select(
            User.id.label("user_id"),
            User.name.label("name"),
            func.round(model.rating).label("rating"),
            func.coalesce(solved.c.cnt, 0).label("solved"),
        )
        .select_from(model)
        .join(User, User.id == model.user_id)
        .outerjoin(solved, solved.c.user_id == User.id)
        .where(eligible, User.is_blocked.is_(False))
        .subquery()
    )


def page(db: Session, board: str, tag: str | None, page_no: int, me_id: int | None) -> dict:
    rows = _rows(board, tag)
    total = db.scalar(select(func.count()).select_from(rows)) or 0
    offset = (page_no - 1) * PAGE_SIZE
    chunk = db.execute(
        select(rows)
        .order_by(rows.c.rating.desc(), rows.c.solved.desc(), rows.c.user_id)
        .offset(offset)
        .limit(PAGE_SIZE)
    ).all()

    items: list[dict] = []
    for i, r in enumerate(chunk):
        rating = int(r.rating)
        if i == 0:
            rank = 1 + (db.scalar(select(func.count()).select_from(rows).where(rows.c.rating > r.rating)) or 0)
        elif rating == items[-1]["rating"]:
            rank = items[-1]["rank"]  # tie
        else:
            rank = offset + i + 1  # everyone before has a strictly higher rating
        items.append(
            {
                "rank": rank, "user_id": r.user_id, "name": r.name, "rating": rating,
                "solved": int(r.solved), "is_me": r.user_id == me_id,
            }
        )
    return {
        "items": items, "total": total, "page": page_no, "page_size": PAGE_SIZE,
        "me": my_position(db, rows, me_id),
    }


def my_position(db: Session, rows, me_id: int | None) -> dict | None:
    if me_id is None:
        return None
    mine = db.execute(select(rows).where(rows.c.user_id == me_id)).first()
    if mine is None:
        return None
    higher = db.scalar(select(func.count()).select_from(rows).where(rows.c.rating > mine.rating)) or 0
    before = db.scalar(
        select(func.count()).select_from(rows).where(
            (rows.c.rating > mine.rating)
            | ((rows.c.rating == mine.rating) & (rows.c.solved > mine.solved))
            | (
                (rows.c.rating == mine.rating)
                & (rows.c.solved == mine.solved)
                & (rows.c.user_id < mine.user_id)
            )
        )
    ) or 0
    return {
        "rank": higher + 1, "position": before + 1, "page": before // PAGE_SIZE + 1,
        "rating": int(mine.rating), "solved": int(mine.solved),
    }
