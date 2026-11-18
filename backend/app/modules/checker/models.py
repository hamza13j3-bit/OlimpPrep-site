from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# Processing states only (not verdicts): queued -> running -> done
STATE_QUEUED = "queued"
STATE_RUNNING = "running"
STATE_DONE = "done"


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        Index("ix_submissions_user_problem", "user_id", "problem_id"),
        Index("ix_submissions_problem_solved", "problem_id", "solved"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"))
    language: Mapped[str] = mapped_column(String(10))
    code: Mapped[str] = mapped_column(Text)
    # Set for submissions made inside a duel (id of the duel match; no FK on purpose, the
    # duel module owns that table). Such submissions never change the training ratings.
    duel_match_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    state: Mapped[str] = mapped_column(String(10), default=STATE_QUEUED, index=True)
    tests_passed: Mapped[int] = mapped_column(Integer, default=0)
    tests_total: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    solved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
