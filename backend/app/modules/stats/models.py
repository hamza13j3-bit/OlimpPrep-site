from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class RetrySchedule(Base):
    """Spaced "retry later" schedule: one row per (user, problem) whose best score is below 1.

    stage indexes RETRY_DAYS (1, 3, 7, 14); next_due_at is when the problem reappears.
    The row is deleted as soon as the problem is solved.
    """

    __tablename__ = "retry_schedule"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), primary_key=True)
    stage: Mapped[int] = mapped_column(Integer, default=0)
    next_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
