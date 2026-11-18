from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.problems.models import (
    DEFAULT_TAGS,
    Hint,
    HintUsage,
    IdeaNote,
    Problem,
    ProblemTest,
    ProblemTranslation,
    Subtask,
    Tag,
    problem_tags,
)
from app.modules.problems.schemas import IdeaNoteIn, ProblemIn

LANG_ORDER = ("kk", "ru", "en")


class ProblemError(Exception):
    pass


class UnknownTags(ProblemError):
    def __init__(self, slugs: list[str]):
        super().__init__(f"Unknown tags: {', '.join(slugs)}")
        self.slugs = slugs


class TagExists(ProblemError):
    pass


# ---- tags ------------------------------------------------------------------


def ensure_default_tags(db: Session) -> None:
    have = set(db.scalars(select(Tag.slug)))
    for slug in DEFAULT_TAGS:
        if slug not in have:
            db.add(Tag(slug=slug))
    db.commit()


def list_tags(db: Session) -> list[Tag]:
    return list(db.scalars(select(Tag).order_by(Tag.slug)))


def create_tag(db: Session, slug: str) -> Tag:
    tag = Tag(slug=slug)
    db.add(tag)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise TagExists from None
    return tag


# ---- problems --------------------------------------------------------------


def get_problem(db: Session, problem_id: int) -> Problem | None:
    return db.get(Problem, problem_id)  # children are loaded eagerly (selectin)


def _fill(db: Session, p: Problem, data: ProblemIn) -> None:
    slugs = list(dict.fromkeys(data.tags))
    tags = list(db.scalars(select(Tag).where(Tag.slug.in_(slugs)))) if slugs else []
    missing = sorted(set(slugs) - {t.slug for t in tags})
    if missing:
        raise UnknownTags(missing)

    p.rating = data.rating
    p.time_limit_ms = data.time_limit_ms
    p.memory_limit_mb = data.memory_limit_mb
    p.source = data.source
    p.year = data.year
    p.author = data.author
    p.hide_tags_until_solved = data.hide_tags_until_solved
    p.tags = tags

    if p.id is not None:
        # Replace children wholesale; flush deletes first so unique keys do not clash.
        p.translations.clear()
        p.subtasks.clear()
        p.hints.clear()
        db.flush()

    for lang, t in data.translations.items():
        p.translations.append(
            ProblemTranslation(
                lang=lang, title=t.title, title_folded=t.title.casefold(), statement=t.statement
            )
        )
    for i, st in enumerate(data.subtasks):
        p.subtasks.append(
            Subtask(
                position=i,
                points=st.points,
                tests=[
                    ProblemTest(
                        position=j, input_data=t.input, output_data=t.output, is_example=t.is_example
                    )
                    for j, t in enumerate(st.tests)
                ],
            )
        )
    for h in data.hints:
        p.hints.append(Hint(level=h.level, lang=h.lang, text=h.text))


def create_problem(db: Session, data: ProblemIn) -> Problem:
    p = Problem()
    try:
        _fill(db, p, data)
    except UnknownTags:
        db.rollback()
        raise
    db.add(p)
    db.commit()
    return p


def update_problem(db: Session, p: Problem, data: ProblemIn) -> Problem:
    try:
        _fill(db, p, data)
    except UnknownTags:
        db.rollback()
        raise
    db.commit()
    return p


def delete_problem(db: Session, p: Problem) -> None:
    db.delete(p)
    db.commit()


def problem_ratings(db: Session) -> list[tuple[int, int]]:
    """(id, rating) of every problem, without loading statements or tests."""
    return [(pid, rating) for pid, rating in db.execute(select(Problem.id, Problem.rating))]


def titles_for(db: Session, ids: list[int], lang: str) -> dict[int, str]:
    """Title per problem id in `lang`, falling back to Kazakh, then any language."""
    if not ids:
        return {}
    by_problem: dict[int, dict[str, str]] = {}
    for pid, tl, title in db.execute(
        select(ProblemTranslation.problem_id, ProblemTranslation.lang, ProblemTranslation.title).where(
            ProblemTranslation.problem_id.in_(ids)
        )
    ):
        by_problem.setdefault(pid, {})[tl] = title
    out = {}
    for pid, titles in by_problem.items():
        out[pid] = next((titles[c] for c in (lang, "kk", *LANG_ORDER) if c in titles), next(iter(titles.values())))
    return out


def existing_ids(db: Session, ids: list[int]) -> set[int]:
    if not ids:
        return set()
    return set(db.scalars(select(Problem.id).where(Problem.id.in_(ids))))


def set_rating(db: Session, problem_id: int, rating: int) -> None:
    """Used by the rating module; the caller commits."""
    p = db.get(Problem, problem_id)
    if p is not None:
        p.rating = rating


# ---- hints -----------------------------------------------------------------


class HintNotFound(ProblemError):
    pass


def _hint_text(p: Problem, level: int, lang: str) -> str | None:
    by_lang = {h.lang: h.text for h in p.hints if h.level == level}
    for candidate in (lang, "kk", *LANG_ORDER):
        if candidate in by_lang:
            return by_lang[candidate]
    return None


def reveal_hint(db: Session, user_id: int, p: Problem, level: int, lang: str) -> str:
    """Return the hint and remember that the user opened this level."""
    text = _hint_text(p, level, lang)
    if text is None:
        raise HintNotFound
    exists = db.scalar(
        select(HintUsage.id).where(
            HintUsage.user_id == user_id, HintUsage.problem_id == p.id, HintUsage.level == level
        )
    )
    if exists is None:
        db.add(HintUsage(user_id=user_id, problem_id=p.id, level=level))
        db.commit()
    return text


def revealed_hints(db: Session, user_id: int, p: Problem, lang: str) -> list[dict]:
    levels = db.scalars(
        select(HintUsage.level)
        .where(HintUsage.user_id == user_id, HintUsage.problem_id == p.id)
        .order_by(HintUsage.level)
    )
    out = []
    for level in levels:
        text = _hint_text(p, level, lang)
        if text is not None:
            out.append({"level": level, "text": text})
    return out


def max_hint_level(db: Session, user_id: int, problem_id: int) -> int:
    return db.scalar(
        select(func.max(HintUsage.level)).where(
            HintUsage.user_id == user_id, HintUsage.problem_id == problem_id
        )
    ) or 0


# ---- views -----------------------------------------------------------------


def pick_translation(p: Problem, lang: str) -> ProblemTranslation:
    """Requested language, else Kazakh (default), else any available."""
    by_lang = {t.lang: t for t in p.translations}
    for candidate in (lang, "kk", *LANG_ORDER):
        if candidate in by_lang:
            return by_lang[candidate]
    raise ProblemError("problem has no translations")  # prevented by schema validation


def tags_visible(p: Problem, solved: bool, is_admin: bool) -> bool:
    return is_admin or solved or not p.hide_tags_until_solved


def public_view(p: Problem, lang: str, solved: bool, is_admin: bool) -> dict:
    tr = pick_translation(p, lang)
    show_tags = tags_visible(p, solved, is_admin)
    return {
        "id": p.id,
        "number": p.id,
        "rating": p.rating,
        "time_limit_ms": p.time_limit_ms,
        "memory_limit_mb": p.memory_limit_mb,
        "source": p.source,
        "year": p.year,
        "author": p.author,
        "tags": [t.slug for t in p.tags] if show_tags else [],
        "tags_hidden": not show_tags,
        "lang": tr.lang,
        "languages": [x for x in LANG_ORDER if any(t.lang == x for t in p.translations)],
        "title": tr.title,
        "statement": tr.statement,
        # only tests flagged as examples are ever exposed
        "examples": [
            {"input": t.input_data, "output": t.output_data}
            for st in p.subtasks
            for t in st.tests
            if t.is_example
        ],
    }


def admin_view(p: Problem) -> dict:
    return {
        "id": p.id,
        "number": p.id,
        "rating": p.rating,
        "time_limit_ms": p.time_limit_ms,
        "memory_limit_mb": p.memory_limit_mb,
        "source": p.source,
        "year": p.year,
        "author": p.author,
        "hide_tags_until_solved": p.hide_tags_until_solved,
        "tags": [t.slug for t in p.tags],
        "translations": {t.lang: {"title": t.title, "statement": t.statement} for t in p.translations},
        "subtasks": [
            {
                "id": st.id,
                "points": st.points,
                "tests": [
                    {"input": t.input_data, "output": t.output_data, "is_example": t.is_example}
                    for t in st.tests
                ],
            }
            for st in p.subtasks
        ],
        "hints": [{"level": h.level, "lang": h.lang, "text": h.text} for h in p.hints],
    }


# ---- idea note ---------------------------------------------------------------


def get_note(db: Session, user_id: int, problem_id: int) -> IdeaNote | None:
    return db.scalar(select(IdeaNote).where(IdeaNote.user_id == user_id, IdeaNote.problem_id == problem_id))


def has_note(db: Session, user_id: int, problem_id: int) -> bool:
    """True when the user may use the editor on this problem (the server enforces it)."""
    return (
        db.scalar(select(IdeaNote.id).where(IdeaNote.user_id == user_id, IdeaNote.problem_id == problem_id))
        is not None
    )


def save_note(db: Session, user_id: int, problem_id: int, data: IdeaNoteIn) -> IdeaNote:
    """Create or replace the user's plan. `data` is already validated (30 words, full checklist)."""
    note = get_note(db, user_id, problem_id)
    if note is None:
        note = IdeaNote(user_id=user_id, problem_id=problem_id)
        db.add(note)
    note.text = data.text.strip()
    note.read_constraints = data.read_constraints
    note.named_algorithm = data.named_algorithm
    note.estimated_complexity = data.estimated_complexity
    note.listed_edge_cases = data.listed_edge_cases
    note.updated_at = datetime.now(timezone.utc)
    db.commit()
    return note


def notes_for_moderation(db: Session, problem_id: int) -> list[dict]:
    """Admin, read-only: every user's plan for a problem."""
    rows = db.execute(
        select(IdeaNote, User.name)
        .join(User, User.id == IdeaNote.user_id)
        .where(IdeaNote.problem_id == problem_id)
        .order_by(IdeaNote.id)
    )
    out = []
    for note, name in rows:
        out.append(
            {
                "user_id": note.user_id,
                "user_name": name,
                "text": note.text,
                "read_constraints": note.read_constraints,
                "named_algorithm": note.named_algorithm,
                "estimated_complexity": note.estimated_complexity,
                "listed_edge_cases": note.listed_edge_cases,
                "updated_at": note.updated_at,
            }
        )
    return out


def tag_info(db: Session, ids: list[int]) -> dict[int, tuple[list[str], bool]]:
    """(tag slugs, hide_tags_until_solved) per problem id, without loading statements or tests."""
    if not ids:
        return {}
    out: dict[int, tuple[list[str], bool]] = {
        pid: ([], hide) for pid, hide in db.execute(select(Problem.id, Problem.hide_tags_until_solved).where(Problem.id.in_(ids)))
    }
    for pid, slug in db.execute(
        select(problem_tags.c.problem_id, Tag.slug)
        .join(Tag, Tag.id == problem_tags.c.tag_id)
        .where(problem_tags.c.problem_id.in_(ids))
        .order_by(Tag.slug)
    ):
        out[pid][0].append(slug)
    return out
