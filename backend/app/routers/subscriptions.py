from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from ..db import get_db
from ..models import User, Subscription
from ..deps import current_user, admin_user
from ..schemas import ActivateSubscriptionIn

router = APIRouter()

def _get_subscription(db, user_id):
    return db.query(Subscription).filter(Subscription.user_id == user_id).first()

@router.get("/status")
def subscription_status(user=Depends(current_user), db: Session = Depends(get_db)):
    sub = _get_subscription(db, user.id)
    if not sub:
        return {"status": "Imeisha", "expires_at": None, "is_active": False}
    now = datetime.utcnow()
    is_active = sub.status == "Hai" and sub.expires_at > now
    return {
        "status": sub.status,
        "expires_at": sub.expires_at.isoformat(),
        "is_active": is_active,
    }

@router.post("/activate")
def activate_subscription(data: ActivateSubscriptionIn, db: Session = Depends(get_db), admin=Depends(admin_user)):
    sub = _get_subscription(db, data.user_id)
    if not sub:
        # Create new subscription
        if data.expires_at:
            expires = data.expires_at
        else:
            # Default: next Sunday 18:59:59
            now = datetime.utcnow()
            days_until_sunday = (6 - now.weekday()) % 7
            expires = now.replace(hour=18, minute=59, second=59, microsecond=0) + timedelta(days=days_until_sunday)
            if days_until_sunday == 0 and now.hour >= 19:
                expires += timedelta(days=7)
        sub = Subscription(
            user_id=data.user_id,
            status="Hai",
            expires_at=expires,
            warning_sms_sent=False,
        )
        db.add(sub)
    else:
        if data.expires_at:
            sub.expires_at = data.expires_at
        else:
            now = datetime.utcnow()
            days_until_sunday = (6 - now.weekday()) % 7
            expires = now.replace(hour=18, minute=59, second=59, microsecond=0) + timedelta(days=days_until_sunday)
            if days_until_sunday == 0 and now.hour >= 19:
                expires += timedelta(days=7)
            sub.expires_at = expires
        sub.status = "Hai"
        sub.warning_sms_sent = False
    db.commit()
    db.refresh(sub)
    return {
        "status": sub.status,
        "expires_at": sub.expires_at.isoformat(),
        "is_active": True,
    }

@router.get("/all")
def list_subscriptions(db: Session = Depends(get_db), admin=Depends(admin_user)):
    subs = db.query(Subscription).all()
    result = []
    for sub in subs:
        user = db.query(User).filter(User.id == sub.user_id).first()
        result.append({
            "id": sub.id,
            "user_id": sub.user_id,
            "phone_number": user.phone_number if user else None,
            "status": sub.status,
            "expires_at": sub.expires_at.isoformat(),
            "warning_sms_sent": sub.warning_sms_sent,
            "updated_at": sub.updated_at.isoformat() if sub.updated_at else None,
        })
    return result