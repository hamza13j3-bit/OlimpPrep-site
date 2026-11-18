import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.modules.problems import models  # noqa: F401
from app.modules.problems.models import DEFAULT_TAGS, Problem
from app.seed.problems_data import COLLECTIONS, build_all
from app.seed.run import seed


@pytest.fixture(scope="module")
def built():
    return build_all()


def test_count_collections_ratings(built):
    assert len(built) >= 30
    assert {c for c, _ in built} == set(COLLECTIONS)
    for c in COLLECTIONS:
        assert sum(1 for x, _ in built if x == c) >= 5
    ratings = [p.rating for _, p in built]
    assert min(ratings) == 800 and max(ratings) <= 2000 and max(ratings) >= 1800


def test_all_tags_used_and_valid(built):
    used = {t for _, p in built for t in p.tags}
    assert used == set(DEFAULT_TAGS)


def test_structure(built):
    titles = set()
    for _, p in built:
        kk = p.translations["kk"]
        assert kk.title not in titles
        titles.add(kk.title)
        assert "**Кіріс.**" in kk.statement and "**Шығыс.**" in kk.statement
        assert sum(s.points for s in p.subtasks) == 100
        assert sum(t.is_example for s in p.subtasks for t in s.tests) == 1
        assert [h.level for h in p.hints] == [1, 2, 3]
        for s in p.subtasks:
            for t in s.tests:
                assert t.input.strip() and t.output.strip()
                assert len(t.input) < 5_000_000


def test_deterministic(built):
    again = build_all()
    assert [p.model_dump() for _, p in built] == [p.model_dump() for _, p in again]


def test_seed_into_db_is_idempotent(built):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        assert seed(db) == len(built)
        assert seed(db) == 0
        assert db.query(Problem).count() == len(built)
