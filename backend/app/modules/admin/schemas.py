from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AdminUserOut(BaseModel):
    id: int
    email: str
    name: str
    school_group: str
    role: str
    is_blocked: bool
    created_at: datetime
    rating: float | None  # overall rating; null = never rated


class AdminUsersPage(BaseModel):
    items: list[AdminUserOut]
    total: int
    page: int
    page_size: int


class DayCount(BaseModel):
    day: str  # YYYY-MM-DD (UTC)
    count: int


class ProblemCount(BaseModel):
    problem_id: int
    title: str
    solved: int


class AdminStats(BaseModel):
    users_total: int
    users_blocked: int
    admins: int
    submissions_total: int
    submissions_per_day: list[DayCount]  # exactly 30 entries, oldest first, zeros included
    most_solved: list[ProblemCount]
    least_solved: list[ProblemCount]


class RatingCorrectionIn(BaseModel):
    scope: Literal["global", "tag", "duel"]
    tag: str | None = Field(None, max_length=30)
    rating: float = Field(ge=0, le=5000)
    reason: str = Field(min_length=5, max_length=500)

    @model_validator(mode="after")
    def _check(self):
        self.reason = self.reason.strip()
        if len(self.reason) < 5:
            raise ValueError("a reason of at least 5 characters is required")
        if (self.scope == "tag") != (self.tag is not None):
            raise ValueError("tag is required for scope 'tag' and not allowed otherwise")
        return self


class RatingCorrectionOut(BaseModel):
    old_rating: float
    new_rating: float


class AuditOut(BaseModel):
    id: int
    admin_id: int
    admin_name: str
    action: str
    target_type: str
    target_id: int | None
    target_label: str
    details: dict
    created_at: datetime


class AuditPage(BaseModel):
    items: list[AuditOut]
    total: int
    page: int
    page_size: int
