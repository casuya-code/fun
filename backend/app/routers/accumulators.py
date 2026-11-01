from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta
from ..db import get_db
from ..models import DailyAccumulator, IndividualMatch, User
from ..deps import current_user, admin_user
from ..schemas import AccumulatorCreate, AccumulatorUpdate, AccumulatorOut, MatchCreate, MatchUpdate, MatchOut

router = APIRouter()

def _serialize_acc(a):
    matches = []
    for m in a.matches:
        matches.append({
            "id": m.id,
            "home_team": m.home_team,
            "away_team": m.away_team,
            "prediction": m.prediction,
            "match_odds": float(m.match_odds),
            "analysis_text": m.analysis_text,
            "status": m.status,
        })
    return {
        "id": a.id,
        "accumulator_date": a.accumulator_date.isoformat(),
        "total_odds": float(a.total_odds),
        "stake_amount": float(a.stake_amount),
        "status": a.status,
        "is_visible": a.is_visible,
        "created_at": a.created_at.isoformat(),
        "matches": matches,
    }

@router.get("/today")
def today_accumulator(db: Session = Depends(get_db), user=Depends(current_user)):
    """Get today's accumulator (Leo screen)."""
    today = datetime.utcnow().date()
    acc = db.query(DailyAccumulator).filter(DailyAccumulator.accumulator_date == today).first()
    if not acc or not acc.is_visible:
        return None
    return _serialize_acc(acc)

@router.get("/history")
def history(days: int = 7, db: Session = Depends(get_db), user=Depends(current_user)):
    """Get accumulator history. days=7 for current week, days=90 for archive."""
    from datetime import timedelta
    start = datetime.utcnow().date() - timedelta(days=days)
    accs = db.query(DailyAccumulator).filter(
        DailyAccumulator.accumulator_date >= start
    ).order_by(DailyAccumulator.accumulator_date.desc()).all()
    
    # Filter visible only for non-admin
    if user.role != "admin":
        accs = [a for a in accs if a.is_visible]
    
    result = []
    for a in accs:
        s = _serialize_acc(a)
        # For history, include status summary
        s["result_status"] = a.status
        result.append(s)
    
    # Summary counters for Siku 90 view
    total = len(result)
    won = len([a for a in accs if a.status == "Won"])
    
    return {
        "accumulators": result,
        "summary": {
            "total": total,
            "won": won,
        }
    }

@router.get("/{acc_id}")
def get_accumulator(acc_id: str, db: Session = Depends(get_db), user=Depends(current_user)):
    acc = db.query(DailyAccumulator).filter(DailyAccumulator.id == acc_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Accumulator haipatikani")
    if not acc.is_visible and user.role != "admin":
        raise HTTPException(status_code=404, detail="Accumulator haipatikani")
    return _serialize_acc(acc)

@router.post("")
def create_accumulator(data: AccumulatorCreate, db: Session = Depends(get_db), admin=Depends(admin_user)):
    # Check if accumulator already exists for this date
    existing = db.query(DailyAccumulator).filter(
        DailyAccumulator.accumulator_date == data.accumulator_date
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Accumulator tayari ipo kwa tarehe hii")
    
    acc = DailyAccumulator(
        accumulator_date=data.accumulator_date,
        total_odds=data.total_odds,
        stake_amount=data.stake_amount,
        status=data.status,
        is_visible=data.is_visible,
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return _serialize_acc(acc)

@router.put("/{acc_id}")
def update_accumulator(acc_id: str, data: AccumulatorUpdate, db: Session = Depends(get_db), admin=Depends(admin_user)):
    acc = db.query(DailyAccumulator).filter(DailyAccumulator.id == acc_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Accumulator haipatikani")
    if data.total_odds is not None:
        acc.total_odds = data.total_odds
    if data.stake_amount is not None:
        acc.stake_amount = data.stake_amount
    if data.status is not None:
        acc.status = data.status
    if data.is_visible is not None:
        acc.is_visible = data.is_visible
    db.commit()
    db.refresh(acc)
    return _serialize_acc(acc)

@router.delete("/{acc_id}")
def delete_accumulator(acc_id: str, db: Session = Depends(get_db), admin=Depends(admin_user)):
    acc = db.query(DailyAccumulator).filter(DailyAccumulator.id == acc_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Accumulator haipatikani")
    db.delete(acc)
    db.commit()
    return {"message": "Accumulator imefutwa"}