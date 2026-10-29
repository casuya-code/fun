import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import User, PasswordResetToken, AuditLog
from ..schemas import RegisterIn, LoginIn, ForgotIn, ResetIn
from ..auth import hash_password, verify_password, create_access_token
from ..deps import current_user
from ..config import settings

router = APIRouter()

@router.post("/register")
def register(data: RegisterIn, request: Request, db: Session = Depends(get_db)):
    # Emails are compared case-insensitively so "User@X.com" and "user@x.com"
    # can never become two accounts, and users can log in with any casing.
    if db.query(User).filter(func.lower(User.email) == data.email.lower()).first():
        raise HTTPException(400, "Barua pepe tayari imesajiliwa")
    if db.query(User).filter(User.nickname == data.nickname).first():
        raise HTTPException(400, "Jina la utani limeshachukuliwa")
    user = User(email=data.email, password_hash=hash_password(data.password), nickname=data.nickname, role="user")
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(400, "Barua pepe au jina la utani tayari linatumika")
    db.refresh(user)
    db.add(AuditLog(user_id=user.id, action="register", ip=request.client.host if request.client else None, detail=data.email))
    db.commit()
    token = create_access_token(user.id, user.role)
    return {"access_token": token, "token_type": "bearer", "user": {"id": user.id, "email": user.email, "nickname": user.nickname, "role": user.role}}

@router.post("/login")
def login(data: LoginIn, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(func.lower(User.email) == data.email.lower()).first()
    ip = request.client.host if request.client else None
    if not user or not verify_password(data.password, user.password_hash):
        db.add(AuditLog(user_id=None, action="login_failed", ip=ip, detail=data.email))
        db.commit()
        raise HTTPException(401, "Taarifa za kuingia si sahihi")
    db.add(AuditLog(user_id=user.id, action="login_success", ip=ip, detail=data.email))
    db.commit()
    token = create_access_token(user.id, user.role)
    return {"access_token": token, "token_type": "bearer", "user": {"id": user.id, "email": user.email, "nickname": user.nickname, "role": user.role}}

@router.post("/forgot")
def forgot(data: ForgotIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(func.lower(User.email) == data.email.lower()).first()
    if user:
        token = secrets.token_urlsafe(32)
        prt = PasswordResetToken(user_id=user.id, token=token, expires_at=datetime.utcnow() + timedelta(hours=1))
        db.add(prt)
        db.commit()
        if settings.debug:
            return {"message": "Kama barua pepe ipo, kiungo cha kuweka upya kimetumwa.", "reset_token": token, "reset_url": f"/reset.html?token={token}"}
    return {"message": "Kama barua pepe ipo, kiungo cha kuweka upya kimetumwa."}

@router.post("/reset")
def reset(data: ResetIn, db: Session = Depends(get_db)):
    prt = db.query(PasswordResetToken).filter(PasswordResetToken.token == data.token, PasswordResetToken.used == False).first()
    if not prt or prt.expires_at < datetime.utcnow():
        raise HTTPException(400, "Kiungo si sahihi au kimekwisha muda")
    user = db.query(User).filter(User.id == prt.user_id).first()
    if not user:
        raise HTTPException(400, "Kiungo si sahihi au kimekwisha muda")
    user.password_hash = hash_password(data.new_password)
    prt.used = True
    db.commit()
    return {"message": "Password updated"}

@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email, "nickname": user.nickname, "role": user.role, "created_at": user.created_at.isoformat()}