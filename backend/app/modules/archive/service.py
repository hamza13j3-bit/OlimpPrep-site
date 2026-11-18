"""Archive listing (Codeforces problemset style) and collections.

The listing runs in a constant number of queries (page rows + translations + tags + count):
solved counts and the user's status come from two aggregate subqueries joined once, never
per-row lookups. It selects plain columns, not Problem entities, because Problem eagerly
loads its tests.
Read-only use of the problems tables is the one place this module reaches below
problems.service; writes always go through services.
"""

from dataclasses import dataclass, field

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.modules.archive.models import Collection, CollectionProblem
from app.modules.auth.models import ROLE_ADMIN, User
from app.modules.checker import service as checker_service
from app.modules.problems import service as problems_service
from app.modules.problems.models import Problem, ProblemTranslation, Tag, problem_tags

PER_PAGE = 50
LANG_ORDER = problems_service.LANG_ORDER
DEFAULT_ORDER = {"number": "asc", "rating": "asc", "solved": "desc", "newest": "desc"}


@dataclass
class Filters:
    tags: list[str] = field(default_factory=list)
    rating_min: int | None = None
    rating_max: int | None = None
    status: str | None = None
    source: str | None = None
    year: int | None = None
    lang: str | None = None
    q: str | None = None


def _like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class _Query:
    """Joins + column expressions shared by the page query and the count query."""

    def __init__(self, user: User | None):
        self.user = user
        self.is_admin = user is not None and user.role == ROLE_ADMIN
        self.solved_by = checker_service.solved_counts_subquery()
        self.mine = checker_service.user_status_subquery(user.id if user else None)
        self.source = Problem.__table__.outerjoin(
            self.solved_by, self.solved_by.c.problem_id == Problem.id
        ).outerjoin(self.mine, self.mine.c.problem_id == Problem.id)
        self.solved_count = func.coalesce(self.solved_by.c.cnt, 0)
        self.attempts = func.coalesce(self.mine.c.attempts, 0)
        self.is_solved = func.coalesce(self.mine.c.solved, 0)

    def conditions(self, f: Filters) -> list:
        c = []
        if f.tags:
            for slug in f.tags:
                c.append(
                    Problem.id.in_(
                        select(problem_tags.c.problem_id).join(Tag, Tag.id == problem_tags.c.tag_id).where(Tag.slug == slug)
                    )
                )
            if not self.is_admin:
                # Never let the tag filter reveal hidden tags: such problems are only
                # matchable by tag once the user has solved them.
                c.append(or_(Problem.hide_tags_until_solved.is_(False), self.is_solved == 1))
        if f.rating_min is not None:
            c.append(Problem.rating >= f.rating_min)
        if f.rating_max is not None:
            c.append(Problem.rating <= f.rating_max)
        if f.source:
            c.append(Problem.source == f.source)
        if f.year is not None:
            c.append(Problem.year == f.year)
        if f.lang:
            c.append(
                exists().where(ProblemTranslation.problem_id == Problem.id, ProblemTranslation.lang == f.lang)
            )
        if f.q and f.q.strip():
            text = f.q.strip().lstrip("#").strip()
            cond = exists().where(
                ProblemTranslation.problem_id == Problem.id,
                ProblemTranslation.title_folded.like(f"%{_like_escape(text.casefold())}%", escape="\\"),
            )
            if text.isdigit():
                cond = or_(cond, Problem.id == int(text))
            c.append(cond)
        if f.status == "solved":
            c.append(self.is_solved == 1)
        elif f.status == "attempted":
            c.append(self.attempts > 0)
            c.append(self.is_solved == 0)
        elif f.status == "unsolved":
            c.append(self.attempts == 0)
        return c

    def columns(self):
        return (
            Problem.id, Problem.rating, Problem.source, Problem.year, Problem.hide_tags_until_solved,
            self.solved_count.label("solved_count"), self.attempts.label("attempts"),
            self.is_solved.label("is_solved"),
        )

    def order_by(self, sort: str, order: str | None):
        direction = order or DEFAULT_ORDER[sort]
        col = {
            "number": Problem.id,
            "rating": Problem.rating,
            "solved": self.solved_count,
            "newest": Problem.created_at,
        }[sort]
        col = col.desc() if direction == "desc" else col.asc()
        return [col, Problem.id.desc() if sort == "newest" else Problem.id.asc()]


def _build_items(db: Session, q: _Query, rows, ui_lang: str) -> list[dict]:
    ids = [r.id for r in rows]
    titles: dict[int, dict[str, str]] = {i: {} for i in ids}
    tags: dict[int, list[str]] = {i: [] for i in ids}
    if ids:
        for pid, lang, title in db.execute(
            select(ProblemTranslation.problem_id, ProblemTranslation.lang, ProblemTranslation.title).where(
                ProblemTranslation.problem_id.in_(ids)
            )
        ):
            titles[pid][lang] = title
        for pid, slug in db.execute(
            select(problem_tags.c.problem_id, Tag.slug)
            .join(Tag, Tag.id == problem_tags.c.tag_id)
            .where(problem_tags.c.problem_id.in_(ids))
            .order_by(Tag.slug)
        ):
            tags[pid].append(slug)
    items = []
    for r in rows:
        by_lang = titles[r.id]
        lang = next(c for c in (ui_lang, "kk", *LANG_ORDER, *by_lang) if c in by_lang)
        show_tags = q.is_admin or not r.hide_tags_until_solved or r.is_solved == 1
        if q.user is None:
            status = None
        elif r.is_solved == 1:
            status = "solved"
        elif r.attempts > 0:
            status = "attempted"
        else:
            status = "unsolved"
        items.append(
            {
                "number": r.id,
                "title": by_lang[lang],
                "lang": lang,
                "languages": [x for x in LANG_ORDER if x in by_lang],
                "tags": tags[r.id] if show_tags else [],
                "tags_hidden": not show_tags,
                "rating": r.rating,
                "solved_count": r.solved_count,
                "status": status,
                "source": r.source,
                "year": r.year,
            }
        )
    return items


def list_problems(
    db: Session, user: User | None, f: Filters, sort: str, order: str | None, page: int, ui_lang: str
) -> dict:
    q = _Query(user)
    conds = q.conditions(f)
    total = db.scalar(select(func.count(Problem.id)).select_from(q.source).where(*conds)) or 0
    rows = db.execute(
        select(*q.columns())
        .select_from(q.source)
        .where(*conds)
        .order_by(*q.order_by(sort, order))
        .limit(PER_PAGE)
        .offset((page - 1) * PER_PAGE)
    ).all()
    return {
        "items": _build_items(db, q, rows, f.lang or ui_lang),
        "total": total,
        "page": page,
        "pages": (total + PER_PAGE - 1) // PER_PAGE,
        "per_page": PER_PAGE,
    }


def problems_by_ids(db: Session, user: User | None, ids: list[int], ui_lang: str) -> list[dict]:
    """Archive rows for specific problems, in the order of `ids`."""
    if not ids:
        return []
    q = _Query(user)
    rows = db.execute(select(*q.columns()).select_from(q.source).where(Problem.id.in_(ids))).all()
    by_id = {it["number"]: it for it in _build_items(db, q, rows, ui_lang)}
    return [by_id[i] for i in ids if i in by_id]


# ---- collections ----------------------------------------------------------------


class CollectionError(Exception):
    pass


class CollectionExists(CollectionError):
    pass


class UnknownProblems(CollectionError):
    def __init__(self, ids: list[int]):
        super().__init__(f"Unknown problem ids: {ids}")
        self.ids = ids


def list_collections(db: Session) -> list[dict]:
    counts = dict(
        db.execute(
            select(CollectionProblem.collection_id, func.count())
            .join(Problem, Problem.id == CollectionProblem.problem_id)
            .group_by(CollectionProblem.collection_id)
        ).all()
    )
    cols = db.scalars(select(Collection).order_by(Collection.id)).all()
    return [
        {"id": c.id, "title": c.title, "description": c.description, "problem_count": counts.get(c.id, 0)}
        for c in cols
    ]


def get_collection(db: Session, collection_id: int) -> Collection | None:
    return db.get(Collection, collection_id)


def collection_detail(db: Session, c: Collection, user: User | None, ui_lang: str) -> dict:
    return {
        "id": c.id,
        "title": c.title,
        "description": c.description,
        "problems": problems_by_ids(db, user, [i.problem_id for i in c.items], ui_lang),
    }


def _set_items(db: Session, c: Collection, problem_ids: list[int]) -> None:
    missing = sorted(set(problem_ids) - problems_service.existing_ids(db, problem_ids))
    if missing:
        raise UnknownProblems(missing)
    if c.id is not None:
        c.items.clear()
        db.flush()
    for pos, pid in enumerate(problem_ids):
        c.items.append(CollectionProblem(problem_id=pid, position=pos))


def _title_taken(db: Session, title: str, except_id: int | None) -> bool:
    q = select(Collection.id).where(Collection.title == title)
    if except_id is not None:
        q = q.where(Collection.id != except_id)
    return db.scalar(q) is not None


def create_collection(db: Session, title: str, description: str, problem_ids: list[int]) -> Collection:
    if _title_taken(db, title, None):
        raise CollectionExists
    c = Collection(title=title, description=description)
    _set_items(db, c, problem_ids)
    db.add(c)
    db.commit()
    return c


def update_collection(db: Session, c: Collection, title: str, description: str, problem_ids: list[int]) -> Collection:
    if _title_taken(db, title, c.id):
        raise CollectionExists
    try:
        c.title, c.description = title, description
        _set_items(db, c, problem_ids)
        db.commit()
    except CollectionError:
        db.rollback()
        raise
    return c


def delete_collection(db: Session, c: Collection) -> None:
    db.delete(c)
    db.commit()


def ensure_collection(db: Session, title: str, problem_ids: list[int]) -> Collection:
    """Seed helper: create the collection or append missing problems (idempotent)."""
    c = db.scalar(select(Collection).where(Collection.title == title))
    if c is None:
        return create_collection(db, title, "", problem_ids)
    have = {i.problem_id for i in c.items}
    new = [p for p in problem_ids if p not in have]
    if new:
        return update_collection(db, c, c.title, c.description, [i.problem_id for i in c.items] + new)
    return c
