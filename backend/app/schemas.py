from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List, Literal
from datetime import datetime, timezone

# bcrypt only accepts passwords up to 72 bytes; anything longer raises and
# would otherwise surface as a 500 error on register/reset.
MAX_PASSWORD_BYTES = 72


def _check_password(v: str) -> str:
    if len(v.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Nenosiri ni refu mno (kiwango cha juu ni baiti {MAX_PASSWORD_BYTES})")
    return v


def _utm(v: datetime) -> datetime:
    """Normalise an aware datetime to UTC and drop the timezone.

    Timestamps in the database are stored as UTC without a timezone. If an
    API client sends "+03:00" or "Z" we must convert before saving, otherwise
    PostgreSQL shifts the value again when casting to the column type.
    """
    if v.tzinfo is not None:
        v = v.astimezone(timezone.utc).replace(tzinfo=None)
    return v


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    nickname: str = Field(min_length=2, max_length=30)

    @field_validator("email", mode="before")
    @classmethod
    def _normalise_email(cls, v):
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("nickname", mode="before")
    @classmethod
    def _strip_nickname(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("nickname")
    @classmethod
    def _non_blank_nickname(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Jina la utani haliwezi kuwa tupu")
        return v

    @field_validator("password")
    @classmethod
    def _password_size(cls, v: str) -> str:
        return _check_password(v)


class LoginIn(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email", mode="before")
    @classmethod
    def _normalise_email(cls, v):
        return v.strip().lower() if isinstance(v, str) else v


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class ForgotIn(BaseModel):
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def _normalise_email(cls, v):
        return v.strip().lower() if isinstance(v, str) else v


class ResetIn(BaseModel):
    token: str
    new_password: str = Field(min_length=6)

    @field_validator("new_password")
    @classmethod
    def _password_size(cls, v: str) -> str:
        return _check_password(v)


class PredictionCreate(BaseModel):
    home_team: str = Field(min_length=1, max_length=80)
    away_team: str = Field(min_length=1, max_length=80)
    match_date: datetime
    odds: float = Field(gt=1.0, le=1000)

    @field_validator("match_date")
    @classmethod
    def _utc_match_date(cls, v: datetime) -> datetime:
        return _utm(v)


class PredictionUpdate(BaseModel):
    home_team: Optional[str] = Field(default=None, min_length=1, max_length=80)
    away_team: Optional[str] = Field(default=None, min_length=1, max_length=80)
    match_date: Optional[datetime] = None
    odds: Optional[float] = Field(default=None, gt=1.0, le=1000)
    status: Optional[Literal["scheduled", "live", "finished"]] = None
    outcome: Optional[Literal["win", "lose", "void"]] = None

    @field_validator("match_date")
    @classmethod
    def _utc_match_date(cls, v):
        return _utm(v) if v is not None else v


class AllowIn(BaseModel):
    allowed: bool


class PickCreate(BaseModel):
    prediction_ids: List[str]


class FollowIn(BaseModel):
    user_id: str
