from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.duel.elo import START_RATING


class DuelRating(Base):
    __tablename__ = "duel_ratings"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    rating: Mapped[float] = mapped_column(Float, default=START_RATING, index=True)
    games: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    draws: Mapped[int] = mapped_column(Integer, default=0)


class DuelMatch(Base):
    __tablename__ = "duel_matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(10), index=True)  # active | finished
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    winner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)  # None + finished = draw
    reason: Mapped[str | None] = mapped_column(String(12), nullable=True)  # all_solved | timeout | forfeit


class DuelParticipant(Base):
    __tablename__ = "duel_participants"
    __table_args__ = (Index("ix_duel_participants_user", "user_id", "match_id"),)

    match_id: Mapped[int] = mapped_column(ForeignKey("duel_matches.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    rating_before: Mapped[float] = mapped_column(Float)
    rating_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DuelMatchProblem(Base):
    __tablename__ = "duel_match_problems"

    match_id: Mapped[int] = mapped_column(ForeignKey("duel_matches.id", ondelete="CASCADE"), primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer)


class DuelPlayerProblem(Base):
    """One player's progress on one match problem."""

    __tablename__ = "duel_player_problems"

    match_id: Mapped[int] = mapped_column(ForeignKey("duel_matches.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), primary_key=True)
    best_score: Mapped[float] = mapped_column(Float, default=0.0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    solved_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)  # None = not solved
