from typing import Literal

from pydantic import BaseModel, Field, model_validator

Status = Literal["solved", "attempted", "unsolved"]


class ArchiveItem(BaseModel):
    number: int
    title: str
    lang: str
    languages: list[str]
    tags: list[str]
    tags_hidden: bool
    rating: int
    solved_count: int
    status: Status | None  # None for anonymous visitors
    source: str
    year: int | None


class ArchivePage(BaseModel):
    items: list[ArchiveItem]
    total: int
    page: int
    pages: int
    per_page: int


class CollectionIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    problem_ids: list[int] = Field(default_factory=list, max_length=500)  # order = display order

    @model_validator(mode="after")
    def _unique(self):
        if len(self.problem_ids) != len(set(self.problem_ids)):
            raise ValueError("duplicate problem ids")
        return self


class CollectionBrief(BaseModel):
    id: int
    title: str
    description: str
    problem_count: int


class CollectionDetail(BaseModel):
    id: int
    title: str
    description: str
    problems: list[ArchiveItem]


class ImportOut(BaseModel):
    problem_id: int
    number: int


class PackageErrorOut(BaseModel):
    file: str
    message: str
