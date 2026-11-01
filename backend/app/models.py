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
    phone_number = Column(String(20), unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="Mteja")
    created_at = Column(DateTime, default=datetime.utcnow)
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")

class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(String, primary_key=True, default=uid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String, nullable=False, default="Imeisha")
    expires_at = Column(DateTime, nullable=False)
    warning_sms_sent = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user = relationship("User", back_populates="subscriptions")

class DailyAccumulator(Base):
    __tablename__ = "daily_accumulators"
    id = Column(String, primary_key=True, default=uid)
    accumulator_date = Column(Date, nullable=False, unique=True, index=True)
    total_odds = Column(Numeric(5, 2), nullable=False)
    stake_amount = Column(Numeric(10, 2), default=5000.00)
    status = Column(String, nullable=False, default="Pending")
    is_visible = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    matches = relationship("IndividualMatch", back_populates="accumulator", cascade="all, delete-orphan")

class IndividualMatch(Base):
    __tablename__ = "individual_matches"
    id = Column(String, primary_key=True, default=uid)
    accumulator_id = Column(String, ForeignKey("daily_accumulators.id"), nullable=False, index=True)
    home_team = Column(String(100), nullable=False)
    away_team = Column(String(100), nullable=False)
    prediction = Column(String(50), nullable=False)
    match_odds = Column(Numeric(4, 2), nullable=False)
    analysis_text = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="Pending")
    accumulator = relationship("DailyAccumulator", back_populates="matches")

class Visit(Base):
    __tablename__ = "visits"
    id = Column(String, primary_key=True, default=uid)
    ip = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class EngineMatch(Base):
    __tablename__ = "engine_matches"
    id = Column(String, primary_key=True, default=uid)
    home_team = Column(String, nullable=False)
    away_team = Column(String, nullable=False)
    match_date = Column(DateTime, nullable=False, index=True)
    odds = Column(Numeric(10, 3), nullable=False)
    over15_pct = Column(Numeric(6, 2), nullable=True)
    avg_goals = Column(Numeric(6, 2), nullable=True)
    league = Column(String, nullable=True)
    match_url = Column(String, nullable=True)
    kickoff_at = Column(DateTime, nullable=True)
    last_checked_at = Column(DateTime, nullable=True)
    used = Column(Boolean, nullable=False, default=False)
    filter_type = Column(String, nullable=False, default="over15")
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("home_team", "away_team", "match_date", name="uq_engine_match"),)

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