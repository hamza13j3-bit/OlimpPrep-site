from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.rating.elo import START_RATING

SCOPE_GLOBAL = "global"


def tag_scope(slug: str) -> str:
    return f"tag:{slug}"


class PlayerRating(Base):
    __tablename__ = "player_ratings"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    rating: Mapped[float] = mapped_column(Float, default=START_RATING)
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class TagRating(Base):
    __tablename__ = "tag_ratings"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    tag: Mapped[str] = mapped_column(String(30), primary_key=True)
    rating: Mapped[float] = mapped_column(Float, default=START_RATING)
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class ProblemRating(Base):
    """Exact (float) problem rating. Problem.rating holds the rounded value shown to users."""

    __tablename__ = "problem_ratings"

    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), primary_key=True)
    rating: Mapped[float] = mapped_column(Float)


class RatingEvent(Base):
    """rating_history: one row per rated submission and scope ('global' or 'tag:<slug>')."""

    __tablename__ = "rating_history"
    __table_args__ = (
        UniqueConstraint("submission_id", "scope"),
        Index("ix_rating_history_user_scope", "user_id", "scope", "id"),
        Index("ix_rating_history_user_problem", "user_id", "problem_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"))
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"))
    scope: Mapped[str] = mapped_column(String(40))
    raw_score: Mapped[float] = mapped_column(Float)
    effective_score: Mapped[float] = mapped_column(Float)  # after the hint penalty
    hint_level: Mapped[int] = mapped_column(Integer, default=0)
    expected: Mapped[float] = mapped_column(Float)
    k: Mapped[float] = mapped_column(Float)
    old_rating: Mapped[float] = mapped_column(Float)
    new_rating: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
