import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import db as core_db
from app.core.config import settings
from app.main import app


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    core_db.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    monkeypatch.setattr(settings, "admin_email", "")
    # duel state that lives in memory must not leak between tests
    from app.modules.duel import presence
    from app.modules.duel.deps import get_session_factory
    from app.modules.duel.waiting import waiting

    waiting.clear()
    presence.clear()
    app.dependency_overrides[get_session_factory] = lambda: Session
    app.dependency_overrides[core_db.get_db] = override
    # Plain (non-context-manager) client: skips lifespan, so the real DB is never created.
    c = TestClient(app)
    c.session_factory = Session  # tests that need direct DB access / a queue
    c.engine = engine
    yield c
    app.dependency_overrides.clear()


def register(client, email="a@example.com", password="password1", name="A"):
    r = client.post("/auth/register", json={"email": email, "password": password, "name": name})
    assert r.status_code == 201, r.text
    return r.json()


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


NOTE_TEXT = " ".join(["plan"] * 30)


def note_body(**over) -> dict:
    body = {
        "text": NOTE_TEXT,
        "read_constraints": True,
        "named_algorithm": True,
        "estimated_complexity": True,
        "listed_edge_cases": True,
    }
    body.update(over)
    return body


def write_note(client, headers: dict, problem_id: int) -> None:
    """Unlock the editor for this user and problem (POST /submissions needs an idea note)."""
    r = client.put(f"/problems/{problem_id}/note", json=note_body(), headers=headers)
    assert r.status_code == 200, r.text
