from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import secrets
import string

from ..db import get_db
from ..models import User, PasswordResetToken, Subscription
from ..schemas import RegisterIn, LoginIn, ForgotIn, ResetIn
from ..auth import hash_password, verify_password, create_access_token
from ..deps import current_user
from ..config import settings

router = APIRouter()

def _find_user_by_phone(db, phone):
    return db.query(User).filter(User.phone_number == phone).first()

@router.post("/register")
def register(data: RegisterIn, db: Session = Depends(get_db)):
    # Check for duplicate phone number
    existing = _find_user_by_phone(db, data.phone_number)
    if existing:
        raise HTTPException(status_code=400, detail="Namba ya simu tayari imesajiliwa")
    
    user = User(
        phone_number=data.phone_number,
        password_hash=hash_password(data.password),
        role="Mteja",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Create subscription (expired by default)
    sub = Subscription(
        user_id=user.id,
        status="Imeisha",
        expires_at=datetime.utcnow(),
    )
    db.add(sub)
    db.commit()
    
    token = create_access_token(user.id, user.role)
    return {"access_token": token, "token_type": "bearer", "user": {
        "id": user.id,
        "phone_number": user.phone_number,
        "role": user.role,
    }}

@router.post("/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = _find_user_by_phone(db, data.phone_number)
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Namba ya simu au nenosiri si sahihi")
    token = create_access_token(user.id, user.role)
    return {"access_token": token, "token_type": "bearer", "user": {
        "id": user.id,
        "phone_number": user.phone_number,
        "role": user.role,
    }}

@router.post("/forgot")
def forgot(data: ForgotIn, db: Session = Depends(get_db)):
    user = _find_user_by_phone(db, data.phone_number)
    if not user:
        # Don't reveal if user exists
        return {"message": "Kama namba ipo, OTP itatumwa"}
    
    # Generate OTP
    otp = "".join(secrets.choice(string.digits) for _ in range(6))
    expires = datetime.utcnow() + timedelta(minutes=10)
    
    # Invalidate old tokens
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used == False
    ).update({"used": True})
    
    token = PasswordResetToken(
        user_id=user.id,
        token=otp,
        expires_at=expires,
    )
    db.add(token)
    db.commit()
    
    # TODO: Send OTP via SMS API (WEB SMS PUSH)
    # For now, return OTP in response (remove in production)
    return {"message": "OTP imetumwa", "otp_dev": otp}

@router.post("/reset")
def reset(data: ResetIn, db: Session = Depends(get_db)):
    # Find valid token
    token = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == data.token,
        PasswordResetToken.used == False,
        PasswordResetToken.expires_at > datetime.utcnow()
    ).first()
    if not token:
        raise HTTPException(status_code=400, detail="OTP si sahihi au imeisha muda")
    
    user = db.query(User).filter(User.id == token.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Mtumiaji hapapatikani")
    
    user.password_hash = hash_password(data.new_password)
    token.used = True
    db.commit()
    return {"message": "Nenosiri limebadilishwa kikamilifu"}

@router.get("/me")
def me(user=Depends(current_user), db: Session = Depends(get_db)):
    sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
    return {
        "id": user.id,
        "phone_number": user.phone_number,
        "role": user.role,
        "created_at": user.created_at.isoformat(),
        "subscription": {
            "status": sub.status if sub else "Imeisha",
            "expires_at": sub.expires_at.isoformat() if sub and sub.expires_at else None,
        } if sub else None,
    }