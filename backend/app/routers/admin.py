from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from ..db import get_db
from ..models import User, Subscription, DailyAccumulator, IndividualMatch
from ..deps import admin_user
from ..schemas import AccumulatorUpdate

router = APIRouter()

@router.get("/users")
def list_users(db: Session = Depends(get_db), admin=Depends(admin_user)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    # Batch-load subscriptions to avoid N+1
    user_ids = [u.id for u in users]
    subs = db.query(Subscription).filter(Subscription.user_id.in_(user_ids)).all() if user_ids else []
    sub_map = {s.user_id: s for s in subs}
    result = []
    for u in users:
        sub = sub_map.get(u.id)
        result.append({
            "id": u.id,
            "phone_number": u.phone_number,
            "role": u.role,
            "created_at": u.created_at.isoformat(),
            "subscription": {
                "status": sub.status if sub else "Imeisha",
                "expires_at": sub.expires_at.isoformat() if sub and sub.expires_at else None,
            } if sub else None,
        })
    return result

@router.get("/accumulators")
def list_accumulators(db: Session = Depends(get_db), admin=Depends(admin_user)):
    accs = db.query(DailyAccumulator).order_by(DailyAccumulator.accumulator_date.desc()).all()
    # Batch-load match counts
    acc_ids = [a.id for a in accs]
    from sqlalchemy import func
    counts = {}
    if acc_ids:
        rows = db.query(IndividualMatch.accumulator_id, func.count(IndividualMatch.id)).filter(
            IndividualMatch.accumulator_id.in_(acc_ids)
        ).group_by(IndividualMatch.accumulator_id).all()
        counts = {r[0]: r[1] for r in rows}
    result = []
    for a in accs:
        result.append({
            "id": a.id,
            "accumulator_date": a.accumulator_date.isoformat(),
            "total_odds": float(a.total_odds),
            "stake_amount": float(a.stake_amount),
            "status": a.status,
            "is_visible": a.is_visible,
            "created_at": a.created_at.isoformat(),
            "match_count": counts.get(a.id, 0),
        })
    return result

@router.post("/accumulators/{acc_id}/toggle-visibility")
def toggle_visibility(acc_id: str, db: Session = Depends(get_db), admin=Depends(admin_user)):
    acc = db.query(DailyAccumulator).filter(DailyAccumulator.id == acc_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Accumulator haipatikani")
    acc.is_visible = not acc.is_visible
    db.commit()
    return {"id": acc.id, "is_visible": acc.is_visible}

@router.delete("/accumulators/{acc_id}")
def delete_accumulator(acc_id: str, db: Session = Depends(get_db), admin=Depends(admin_user)):
    acc = db.query(DailyAccumulator).filter(DailyAccumulator.id == acc_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Accumulator haipatikani")
    db.delete(acc)
    db.commit()
    return {"message": "Accumulator imefutwa"}

@router.get("/history")
def admin_history(db: Session = Depends(get_db), admin=Depends(admin_user)):
    accs = db.query(DailyAccumulator).order_by(DailyAccumulator.accumulator_date.desc()).all()
    acc_ids = [a.id for a in accs]
    from sqlalchemy import func
    counts = {}
    if acc_ids:
        rows = db.query(IndividualMatch.accumulator_id, func.count(IndividualMatch.id)).filter(
            IndividualMatch.accumulator_id.in_(acc_ids)
        ).group_by(IndividualMatch.accumulator_id).all()
        counts = {r[0]: r[1] for r in rows}
    result = []
    for a in accs:
        result.append({
            "id": a.id,
            "accumulator_date": a.accumulator_date.isoformat(),
            "total_odds": float(a.total_odds),
            "status": a.status,
            "is_visible": a.is_visible,
            "match_count": counts.get(a.id, 0),
        })
    return result