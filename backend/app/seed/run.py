"""Seed the database: `python -m app.seed.run` (idempotent, matches problems by Kazakh title)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import Base, SessionLocal, engine
from app.modules.archive import models as _archive  # noqa: F401
from app.modules.archive import service as archive_service
from app.modules.auth import models as _auth  # noqa: F401
from app.modules.checker import models as _checker  # noqa: F401
from app.modules.problems import models as _problems  # noqa: F401
from app.modules.problems import service
from app.modules.problems.models import ProblemTranslation
from app.modules.rating import models as _rating  # noqa: F401
from app.seed.problems_data import build_all


def seed(db: Session) -> int:
    """Create missing seed problems and their collections; returns how many problems were added."""
    service.ensure_default_tags(db)
    existing = {
        title: pid
        for pid, title in db.execute(
            select(ProblemTranslation.problem_id, ProblemTranslation.title).where(ProblemTranslation.lang == "kk")
        )
    }
    added = 0
    by_collection: dict[str, list[int]] = {}
    for collection, data in build_all():
        title = data.translations["kk"].title
        if title in existing:
            pid = existing[title]
        else:
            pid = service.create_problem(db, data).id
            added += 1
        by_collection.setdefault(collection, []).append(pid)
    for collection, ids in by_collection.items():
        archive_service.ensure_collection(db, collection, ids)
    return added


if __name__ == "__main__":
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        print(f"Added {seed(session)} problems")
