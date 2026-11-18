from typing import Callable

from sqlalchemy.orm import Session

from app.core.db import SessionLocal


def get_session_factory() -> Callable[[], Session]:
    """Sessions for long-lived work (WebSocket, supervisor). Overridden in tests."""
    return SessionLocal
