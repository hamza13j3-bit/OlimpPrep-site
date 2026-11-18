from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


def _r2(v: float) -> float:
    return round(v, 2)


class TagRatingOut(BaseModel):
    tag: str
    rating: float
    attempts: int

    _round = field_validator("rating")(_r2)


class RatingOut(BaseModel):
    rating: float
    attempts: int
    tags: list[TagRatingOut]

    _round = field_validator("rating")(_r2)


class HistoryPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    submission_id: int
    problem_id: int
    old_rating: float
    new_rating: float
    created_at: datetime

    _round = field_validator("old_rating", "new_rating")(_r2)
