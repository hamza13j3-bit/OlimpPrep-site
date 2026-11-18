from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

DEFAULT_TAGS = (
    "sorting",
    "recursion",
    "dp",
    "graphs",
    "strings",
    "math",
    "greedy",
    "binary-search",
)

problem_tags = Table(
    "problem_tags",
    Base.metadata,
    Column("problem_id", ForeignKey("problems.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(30), unique=True, index=True)


class Problem(Base):
    """Problem number == id (Codeforces-style numbering)."""

    __tablename__ = "problems"

    id: Mapped[int] = mapped_column(primary_key=True)
    rating: Mapped[int] = mapped_column(Integer, default=1200, index=True)
    time_limit_ms: Mapped[int] = mapped_column(Integer, default=1000)
    memory_limit_mb: Mapped[int] = mapped_column(Integer, default=256)
    source: Mapped[str] = mapped_column(String(200), default="", index=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    author: Mapped[str] = mapped_column(String(200), default="")
    hide_tags_until_solved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    tags: Mapped[list[Tag]] = relationship(secondary=problem_tags, lazy="selectin", order_by=Tag.slug)
    translations: Mapped[list["ProblemTranslation"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="ProblemTranslation.id"
    )
    subtasks: Mapped[list["Subtask"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="Subtask.position"
    )
    hints: Mapped[list["Hint"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="(Hint.level, Hint.id)"
    )


class ProblemTranslation(Base):
    __tablename__ = "problem_translations"
    __table_args__ = (UniqueConstraint("problem_id", "lang"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), index=True)
    lang: Mapped[str] = mapped_column(String(2))
    title: Mapped[str] = mapped_column(String(200))
    # casefolded copy for search: SQLite LIKE only folds ASCII, so Cyrillic needs this
    title_folded: Mapped[str] = mapped_column(String(200), default="", index=True)
    statement: Mapped[str] = mapped_column(Text)  # Markdown + LaTeX (incl. input/output format)


class Subtask(Base):
    __tablename__ = "subtasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    points: Mapped[int] = mapped_column(Integer)

    tests: Mapped[list["ProblemTest"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="ProblemTest.position"
    )


class ProblemTest(Base):
    __tablename__ = "problem_tests"

    id: Mapped[int] = mapped_column(primary_key=True)
    subtask_id: Mapped[int] = mapped_column(ForeignKey("subtasks.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    input_data: Mapped[str] = mapped_column(Text)
    output_data: Mapped[str] = mapped_column(Text)
    is_example: Mapped[bool] = mapped_column(Boolean, default=False)


class HintUsage(Base):
    """Which hint levels a user has opened (the deepest one reduces their rated score)."""

    __tablename__ = "hint_usages"
    __table_args__ = (UniqueConstraint("user_id", "problem_id", "level"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), index=True)
    level: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Hint(Base):
    """level 1 = direction, 2 = algorithm name, 3 = pseudocode."""

    __tablename__ = "hints"
    __table_args__ = (UniqueConstraint("problem_id", "level", "lang"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), index=True)
    level: Mapped[int] = mapped_column(Integer)
    lang: Mapped[str] = mapped_column(String(2))
    text: Mapped[str] = mapped_column(Text)


class IdeaNote(Base):
    """Private plan a user writes before coding a problem (one per user and problem).

    Only the author reads it; admins may read it for moderation (read-only).
    """

    __tablename__ = "idea_notes"
    __table_args__ = (UniqueConstraint("user_id", "problem_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    read_constraints: Mapped[bool] = mapped_column(Boolean, default=False)
    named_algorithm: Mapped[bool] = mapped_column(Boolean, default=False)
    estimated_complexity: Mapped[bool] = mapped_column(Boolean, default=False)
    listed_edge_cases: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
