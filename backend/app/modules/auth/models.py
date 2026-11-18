from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

ROLE_USER = "user"
ROLE_ADMIN = "admin"
LANGUAGES = ("kk", "ru", "en")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(100))
    school_group: Mapped[str] = mapped_column(String(100), default="")
    language: Mapped[str] = mapped_column(String(2), default="kk")
    role: Mapped[str] = mapped_column(String(10), default=ROLE_USER)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
