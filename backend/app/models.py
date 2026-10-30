import uuid
from datetime import datetime, date
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Date, Numeric, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from .db import Base

def uid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=uid)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    nickname = Column(String, unique=True, nullable=False, index=True)
    role = Column(String, nullable=False, default="user")  # admin/user
    profile_emoji = Column(String, nullable=True, default="⚽")  # emoji for profile display
    profile_color = Column(String, nullable=True, default="#1a73e8")  # accent color for profile display
    created_at = Column(DateTime, default=datetime.utcnow)
    picks = relationship("UserPick", back_populates="user", cascade="all, delete-orphan")
    following = relationship("Follow", foreign_keys="Follow.follower_id", back_populates="follower", cascade="all, delete-orphan")
    followers = relationship("Follow", foreign_keys="Follow.following_id", back_populates="following", cascade="all, delete-orphan")

class Prediction(Base):
    __tablename__ = "predictions"
    id = Column(String, primary_key=True, default=uid)
    home_team = Column(String, nullable=False)
    away_team = Column(String, nullable=False)
    match_date = Column(DateTime, nullable=False, index=True)
    odds = Column(Numeric(10, 3), nullable=False)
    status = Column(String, nullable=False, default="scheduled")  # scheduled/live/finished
    outcome = Column(String, nullable=True)  # win/lose/void
    home_goals = Column(Integer, nullable=True)  # final score, only when verified
    away_goals = Column(Integer, nullable=True)
    allowed = Column(Boolean, nullable=False, default=False)
    allowed_at = Column(DateTime, nullable=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class UserPick(Base):
    __tablename__ = "user_picks"
    id = Column(String, primary_key=True, default=uid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    combined_odds = Column(Numeric(10, 3), nullable=False)
    user = relationship("User", back_populates="picks")
    legs = relationship("UserPickLeg", back_populates="pick", cascade="all, delete-orphan")

class UserPickLeg(Base):
    __tablename__ = "user_pick_legs"
    id = Column(String, primary_key=True, default=uid)
    pick_id = Column(String, ForeignKey("user_picks.id"), nullable=False, index=True)
    prediction_id = Column(String, ForeignKey("predictions.id"), nullable=False)
    odds = Column(Numeric(10, 3), nullable=False)
    pick = relationship("UserPick", back_populates="legs")
    prediction = relationship("Prediction")

class Follow(Base):
    __tablename__ = "follows"
    id = Column(String, primary_key=True, default=uid)
    follower_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    following_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    follower = relationship("User", foreign_keys=[follower_id], back_populates="following")
    following = relationship("User", foreign_keys=[following_id], back_populates="followers")
    __table_args__ = (UniqueConstraint("follower_id", "following_id", name="uq_follow"),)

class Visit(Base):
    __tablename__ = "visits"
    id = Column(String, primary_key=True, default=uid)
    ip = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=True, index=True)  # set only for logged-in visits
    created_at = Column(DateTime, default=datetime.utcnow)

class EngineMatch(Base):
    """Private admin-only data source for the accumulator engine."""
    __tablename__ = "engine_matches"
    id = Column(String, primary_key=True, default=uid)
    home_team = Column(String, nullable=False)
    away_team = Column(String, nullable=False)
    match_date = Column(DateTime, nullable=False, index=True)
    odds = Column(Numeric(10, 3), nullable=False)
    over15_pct = Column(Numeric(6, 2), nullable=True)   # % of last matches with 2+ goals
    avg_goals = Column(Numeric(6, 2), nullable=True)    # historical average goals
    league = Column(String, nullable=True)
    match_url = Column(String, nullable=True)           # page holding the final result
    kickoff_at = Column(DateTime, nullable=True)        # real kickoff (from the match page)
    last_checked_at = Column(DateTime, nullable=True)   # throttle result lookups
    used = Column(Boolean, nullable=False, default=False)  # whether already used in a generated slip
    filter_type = Column(String, nullable=False, default="over15")
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("home_team", "away_team", "match_date", name="uq_engine_match"),)

class EngineSlip(Base):
    """An admin-only test accumulator. Never visible to normal users."""
    __tablename__ = "engine_slips"
    id = Column(String, primary_key=True, default=uid)
    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    combined_odds = Column(Numeric(10, 3), nullable=False)
    win_prob = Column(Numeric(8, 4), nullable=True)     # estimated probability of the slip
    kelly_stake = Column(Numeric(8, 4), nullable=True)  # fraction of bankroll (1/4 Kelly)
    status = Column(String, nullable=False, default="draft")  # draft/settled
    note = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    legs = relationship("EngineSlipLeg", back_populates="slip", cascade="all, delete-orphan")

class EngineSlipLeg(Base):
    __tablename__ = "engine_slip_legs"
    id = Column(String, primary_key=True, default=uid)
    slip_id = Column(String, ForeignKey("engine_slips.id"), nullable=False, index=True)
    match_id = Column(String, ForeignKey("engine_matches.id"), nullable=False)
    odds = Column(Numeric(10, 3), nullable=False)
    outcome = Column(String, nullable=True)  # win/lose
    home_goals = Column(Integer, nullable=True)
    away_goals = Column(Integer, nullable=True)
    slip = relationship("EngineSlip", back_populates="legs")
    match = relationship("EngineMatch")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(String, primary_key=True, default=uid)
    user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    action = Column(String, nullable=False, index=True)
    ip = Column(String, nullable=True)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    id = Column(String, primary_key=True, default=uid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    token = Column(String, unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)