from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from ..db import get_db
from ..models import UserPick, UserPickLeg, Prediction
from ..schemas import PickCreate
from ..deps import current_user

router = APIRouter()

MIN_ODDS = 1.5
MAX_ODDS = 6.0
MAX_LEGS = 5
HISTORY_DAYS = 60

def compute_combined(preds):
    odds = 1.0
    for p in preds:
        odds *= float(p.odds)
    return round(odds, 3)

def ensure_selectable(preds):
    """Only matches that have not started can be added to a slip."""
    now = datetime.now()
    for p in preds:
        if p.status in ("live", "finished") or p.match_date <= now:
            raise HTTPException(400, f"Mechi imeanza au imemalizika: {p.home_team} vs {p.away_team}")

def pick_status(pick):
    outcomes = [leg.prediction.outcome for leg in pick.legs]
    if not outcomes:
        return "pending"
    if any(o == "lose" for o in outcomes):
        return "lost"
    if any(o is None for o in outcomes):
        return "pending"
    if any(o == "win" for o in outcomes):
        return "won"
    # every leg postponed/cancelled - the stake is refunded
    return "void"

def serialize_pick(pick):
    return {
        "id": pick.id,
        "created_at": pick.created_at.isoformat(),
        "updated_at": pick.updated_at.isoformat(),
        "combined_odds": float(pick.combined_odds),
        "status": pick_status(pick),
        "legs": [
            {
                "prediction_id": leg.prediction_id,
                "home_team": leg.prediction.home_team,
                "away_team": leg.prediction.away_team,
                "match_date": leg.prediction.match_date.isoformat(),
                "odds": float(leg.odds),
                "status": leg.prediction.status,
                "outcome": leg.prediction.outcome,
                "home_goals": leg.prediction.home_goals,
                "away_goals": leg.prediction.away_goals,
                "score": (f"{leg.prediction.home_goals}-{leg.prediction.away_goals}"
                          if leg.prediction.home_goals is not None
                          and leg.prediction.away_goals is not None else None),
            } for leg in pick.legs
        ],
    }

@router.get("")
def list_picks(db: Session = Depends(get_db), user=Depends(current_user)):
    since = datetime.now() - timedelta(days=HISTORY_DAYS)
    picks = db.query(UserPick).filter(UserPick.user_id == user.id, UserPick.created_at >= since).order_by(UserPick.created_at.desc()).all()
    return [serialize_pick(p) for p in picks]

@router.post("")
def create_pick(data: PickCreate, db: Session = Depends(get_db), user=Depends(current_user)):
    if not data.prediction_ids or len(data.prediction_ids) > MAX_LEGS:
        raise HTTPException(400, f"Chagua 1 hadi {MAX_LEGS} machaguo")
    preds = db.query(Prediction).filter(Prediction.id.in_(data.prediction_ids), Prediction.allowed == True).all()
    if len(preds) != len(set(data.prediction_ids)):
        raise HTTPException(400, "Baadhi ya utabiri haziruhusiwi au hazipatikani")
    # unique
    if len(set(data.prediction_ids)) != len(data.prediction_ids):
        raise HTTPException(400, "Utabiri kurudia")
    ensure_selectable(preds)
    combined = compute_combined(preds)
    if combined < MIN_ODDS or combined > MAX_ODDS:
        raise HTTPException(400, f"Odds jumla lazima iwe kati ya {MIN_ODDS} na {MAX_ODDS}")
    pick = UserPick(user_id=user.id, combined_odds=combined)
    db.add(pick)
    db.flush()
    for pid in data.prediction_ids:
        p = next(x for x in preds if x.id == pid)
        leg = UserPickLeg(pick_id=pick.id, prediction_id=pid, odds=p.odds)
        db.add(leg)
    db.commit()
    db.refresh(pick)
    return serialize_pick(pick)

@router.put("/{pick_id}")
def update_pick(pick_id: str, data: PickCreate, db: Session = Depends(get_db), user=Depends(current_user)):
    pick = db.query(UserPick).filter(UserPick.id == pick_id, UserPick.user_id == user.id).first()
    if not pick:
        raise HTTPException(404, "Hakupatikani")
    # editable only if all current legs not live/settled
    for leg in pick.legs:
        if leg.prediction.status in ("live", "finished"):
            raise HTTPException(400, "Haiwezi kuhariri: mechi ipo live au imemalizika")
    if not data.prediction_ids or len(data.prediction_ids) > MAX_LEGS:
        raise HTTPException(400, f"Chagua 1 hadi {MAX_LEGS} machaguo")
    preds = db.query(Prediction).filter(Prediction.id.in_(data.prediction_ids), Prediction.allowed == True).all()
    if len(preds) != len(set(data.prediction_ids)):
        raise HTTPException(400, "Baadhi ya utabiri haziruhusiwi au hazipatikani")
    if len(set(data.prediction_ids)) != len(data.prediction_ids):
        raise HTTPException(400, "Utabiri kurudia")
    for p in preds:
        if p.status in ("live", "finished"):
            raise HTTPException(400, "Haiwezi kujumuisha mechi live/iliyomalizika")
    ensure_selectable(preds)
    combined = compute_combined(preds)
    if combined < MIN_ODDS or combined > MAX_ODDS:
        raise HTTPException(400, f"Odds jumla lazima iwe kati ya {MIN_ODDS} na {MAX_ODDS}")
    # replace legs
    for leg in list(pick.legs):
        db.delete(leg)
    db.flush()
    pick.combined_odds = combined
    pick.updated_at = datetime.now()
    for pid in data.prediction_ids:
        p = next(x for x in preds if x.id == pid)
        leg = UserPickLeg(pick_id=pick.id, prediction_id=pid, odds=p.odds)
        db.add(leg)
    db.commit()
    db.refresh(pick)
    return serialize_pick(pick)