from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_CODE_CHARS = 64 * 1024


class SubmitIn(BaseModel):
    problem_id: int
    language: Literal["python", "cpp"]
    code: str = Field(min_length=1, max_length=MAX_CODE_CHARS)


class SubmittedOut(BaseModel):
    id: int


class SubmissionResult(BaseModel):
    """The only result the server ever reports: no verdict labels."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tests_passed: int
    tests_total: int
    score: float
    solved: bool


class SubmissionListItem(SubmissionResult):
    problem_id: int
    language: str
    created_at: datetime


class ProblemSummary(BaseModel):
    solved_count: int
    best_score: float
