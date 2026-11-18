from pydantic import BaseModel, field_validator


class TagStat(BaseModel):
    tag: str
    avg_score: float  # mean of the best score per attempted problem, in [0, 1]
    attempted: int
    solved: int

    _round = field_validator("avg_score")(lambda v: round(v, 3))


class RetryItem(BaseModel):
    problem_id: int
    title: str
    best_score: float
    stage: int  # 0..3 -> repeats after 1, 3, 7, 14 days
    due: bool
    next_due_at: str  # ISO 8601, UTC

    _round = field_validator("best_score")(lambda v: round(v, 3))


class StatsOut(BaseModel):
    tags: list[TagStat]
    retry: list[RetryItem]
