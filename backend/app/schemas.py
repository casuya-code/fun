from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime, timezone

MAX_PASSWORD_BYTES = 72

def _check_password(v: str) -> str:
    if len(v.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Nenosiri ni refu mno (kiwango cha juu ni baiti {MAX_PASSWORD_BYTES})")
    return v

def _utm(v: datetime) -> datetime:
    if v.tzinfo is not None:
        v = v.astimezone(timezone.utc).replace(tzinfo=None)
    return v

# --- Auth ---
class RegisterIn(BaseModel):
    phone_number: str = Field(min_length=9, max_length=15)
    password: str = Field(min_length=6)

    @field_validator("phone_number", mode="before")
    @classmethod
    def _strip_phone(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("password")
    @classmethod
    def _password_size(cls, v: str) -> str:
        return _check_password(v)

class LoginIn(BaseModel):
    phone_number: str
    password: str

    @field_validator("phone_number", mode="before")
    @classmethod
    def _strip_phone(cls, v):
        return v.strip() if isinstance(v, str) else v

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

class ForgotIn(BaseModel):
    phone_number: str

    @field_validator("phone_number", mode="before")
    @classmethod
    def _strip_phone(cls, v):
        return v.strip() if isinstance(v, str) else v

class ResetIn(BaseModel):
    token: str  # OTP token
    new_password: str = Field(min_length=6)

    @field_validator("new_password")
    @classmethod
    def _password_size(cls, v: str) -> str:
        return _check_password(v)

class OtpVerifyIn(BaseModel):
    phone_number: str
    otp: str

# --- Subscription ---
class SubscriptionStatusOut(BaseModel):
    status: str  # Hai / Imeisha
    expires_at: Optional[datetime] = None
    is_active: bool

class ActivateSubscriptionIn(BaseModel):
    user_id: str
    expires_at: Optional[datetime] = None

# --- Accumulator ---
class AccumulatorCreate(BaseModel):
    accumulator_date: str  # YYYY-MM-DD
    total_odds: float
    stake_amount: float = 5000.00
    status: str = "Pending"
    is_visible: bool = True

class AccumulatorUpdate(BaseModel):
    total_odds: Optional[float] = None
    stake_amount: Optional[float] = None
    status: Optional[str] = None
    is_visible: Optional[bool] = None

class AccumulatorOut(BaseModel):
    id: str
    accumulator_date: str
    total_odds: float
    stake_amount: float
    status: str
    is_visible: bool
    created_at: str
    matches: List[dict] = []

# --- Individual Match ---
class MatchCreate(BaseModel):
    accumulator_id: str
    home_team: str = Field(min_length=1, max_length=100)
    away_team: str = Field(min_length=1, max_length=100)
    prediction: str = Field(min_length=1, max_length=50)
    match_odds: float = Field(gt=1.0, le=1000)
    analysis_text: str = Field(min_length=1)
    status: str = "Pending"

class MatchUpdate(BaseModel):
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    prediction: Optional[str] = None
    match_odds: Optional[float] = None
    analysis_text: Optional[str] = None
    status: Optional[str] = None

class MatchOut(BaseModel):
    id: str
    accumulator_id: str
    home_team: str
    away_team: str
    prediction: str
    match_odds: float
    analysis_text: str
    status: str