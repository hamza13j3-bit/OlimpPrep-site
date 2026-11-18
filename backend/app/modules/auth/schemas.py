from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
Lang = Literal["kk", "ru", "en"]


def _norm_email(v: str) -> str:
    return v.strip().lower()


class RegisterIn(BaseModel):
    email: str = Field(pattern=EMAIL_RE, max_length=254)
    password: str = Field(min_length=8, max_length=72)
    name: str = Field(min_length=1, max_length=100)
    school_group: str = Field(default="", max_length=100)
    language: Lang = "kk"

    _email = field_validator("email", mode="before")(lambda v: _norm_email(v) if isinstance(v, str) else v)


class LoginIn(BaseModel):
    email: str
    password: str = Field(max_length=72)

    _email = field_validator("email", mode="before")(lambda v: _norm_email(v) if isinstance(v, str) else v)


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    school_group: str | None = Field(default=None, max_length=100)
    language: Lang | None = None


class BlockIn(BaseModel):
    blocked: bool


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    school_group: str
    language: str
    role: str
    is_blocked: bool


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
