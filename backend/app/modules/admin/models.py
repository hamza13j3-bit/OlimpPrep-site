from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AuditLog(Base):
    """Append-only record of what an admin did. There is no API to edit or delete rows."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_created", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(40))  # e.g. user.block, rating.adjust, problem.create
    target_type: Mapped[str] = mapped_column(String(20))  # user | problem | tag | collection
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_label: Mapped[str] = mapped_column(String(200), default="")  # snapshot: email, title...
    details: Mapped[str] = mapped_column(Text, default="{}")  # JSON (old/new values, reason)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
