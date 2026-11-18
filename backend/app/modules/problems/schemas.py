from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Lang = Literal["kk", "ru", "en"]
MAX_TEST_CHARS = 5 * 1024 * 1024  # 5 MB per test file (same limit as the ZIP importer)


class TranslationIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    statement: str = Field(min_length=1, max_length=100_000)


class TestIn(BaseModel):
    __test__ = False  # not a pytest class

    input: str = Field(max_length=MAX_TEST_CHARS)
    output: str = Field(max_length=MAX_TEST_CHARS)
    is_example: bool = False


class SubtaskIn(BaseModel):
    points: int = Field(ge=1, le=1000)
    tests: list[TestIn] = Field(min_length=1, max_length=200)


class HintIn(BaseModel):
    level: int = Field(ge=1, le=3)
    lang: Lang
    text: str = Field(min_length=1, max_length=5000)


class TagIn(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,29}$")


class ProblemIn(BaseModel):
    rating: int = Field(default=1200, ge=100, le=4000)
    time_limit_ms: int = Field(default=1000, ge=100, le=10_000)
    memory_limit_mb: int = Field(default=256, ge=16, le=1024)
    source: str = Field(default="", max_length=200)
    year: int | None = Field(default=None, ge=1990, le=2100)
    author: str = Field(default="", max_length=200)
    hide_tags_until_solved: bool = False
    tags: list[str] = Field(default_factory=list, max_length=20)
    translations: dict[Lang, TranslationIn] = Field(min_length=1)
    subtasks: list[SubtaskIn] = Field(min_length=1, max_length=50)
    hints: list[HintIn] = Field(default_factory=list, max_length=9)

    @model_validator(mode="after")
    def _unique_hints(self):
        keys = [(h.level, h.lang) for h in self.hints]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate hint (level, lang)")
        return self


# ---- outputs -------------------------------------------------------------


class Example(BaseModel):
    input: str
    output: str


class ProblemPublic(BaseModel):
    id: int
    number: int
    rating: int
    time_limit_ms: int
    memory_limit_mb: int
    source: str
    year: int | None
    author: str
    tags: list[str]
    tags_hidden: bool
    lang: Lang
    languages: list[Lang]
    title: str
    statement: str
    examples: list[Example]


class TestOut(BaseModel):
    __test__ = False

    input: str
    output: str
    is_example: bool


class SubtaskOut(BaseModel):
    id: int
    points: int
    tests: list[TestOut]


class ProblemAdminOut(BaseModel):
    id: int
    number: int
    rating: int
    time_limit_ms: int
    memory_limit_mb: int
    source: str
    year: int | None
    author: str
    hide_tags_until_solved: bool
    tags: list[str]
    translations: dict[Lang, TranslationIn]
    subtasks: list[SubtaskOut]
    hints: list[HintIn]


class TagOut(BaseModel):
    slug: str


class HintRevealed(BaseModel):
    level: int
    text: str


# ---- idea note ---------------------------------------------------------------

MIN_NOTE_WORDS = 30
MAX_NOTE_CHARS = 5000


def count_words(text: str) -> int:
    return len(text.split())


class IdeaNoteFields(BaseModel):
    text: str
    read_constraints: bool
    named_algorithm: bool
    estimated_complexity: bool
    listed_edge_cases: bool


class IdeaNoteIn(IdeaNoteFields):
    text: str = Field(max_length=MAX_NOTE_CHARS)

    @model_validator(mode="after")
    def _complete(self):
        if count_words(self.text) < MIN_NOTE_WORDS:
            raise ValueError(f"the plan needs at least {MIN_NOTE_WORDS} words")
        if not (
            self.read_constraints
            and self.named_algorithm
            and self.estimated_complexity
            and self.listed_edge_cases
        ):
            raise ValueError("every checklist item must be ticked")
        return self


class IdeaNoteOut(IdeaNoteFields):
    model_config = ConfigDict(from_attributes=True)

    updated_at: datetime


class IdeaNoteModerationOut(IdeaNoteOut):
    user_id: int
    user_name: str
