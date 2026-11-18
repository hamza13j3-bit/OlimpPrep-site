from pydantic import BaseModel


class LeaderRow(BaseModel):
    rank: int
    user_id: int
    name: str
    rating: int
    solved: int
    is_me: bool = False


class MyPosition(BaseModel):
    rank: int
    position: int  # 1-based place in the table order (differs from rank only for ties)
    page: int  # page that contains the row
    rating: int
    solved: int


class LeaderPage(BaseModel):
    items: list[LeaderRow]
    total: int
    page: int
    page_size: int
    me: MyPosition | None = None  # null: anonymous, unrated or blocked
