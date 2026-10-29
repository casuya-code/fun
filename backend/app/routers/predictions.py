from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta
from ..db import get_db
from ..models import Prediction
from ..deps import current_user

router = APIRouter()

def parse_date(d: str):
    try:
        return datetime.strptime(d, "%Y-%m-%d").date()
    except Exception:
        return datetime.utcnow().date()

@router.get("/allowed")
def allowed_predictions(date: str = Query(default=None), include_finished: bool = Query(default=False), db: Session = Depends(get_db), user=Depends(current_user)):
    d = parse_date(date) if date else datetime.utcnow().date()
    start = datetime.combine(d, datetime.min.time())
    end = start + timedelta(days=1)
    now = datetime.utcnow()
    q = db.query(Prediction).filter(
        Prediction.allowed == True,
        Prediction.match_date >= start,
        Prediction.match_date < end
    )
    if not include_finished:
        q = q.filter(Prediction.match_date > now, Prediction.status != "finished")
    preds = q.order_by(Prediction.match_date).all()
    return [serialize(p) for p in preds]

def serialize(p):
    return {
        "id": p.id,
        "home_team": p.home_team,
        "away_team": p.away_team,
        "match_date": p.match_date.isoformat(),
        "odds": float(p.odds),
        "status": p.status,
        "outcome": p.outcome,
        "allowed": p.allowed,
        "allowed_at": p.allowed_at.isoformat() if p.allowed_at else None,
    }