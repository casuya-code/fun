from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import IndividualMatch, DailyAccumulator
from ..deps import current_user, admin_user
from ..schemas import MatchCreate, MatchUpdate, MatchOut

router = APIRouter()

def _serialize(m):
    return {
        "id": m.id,
        "accumulator_id": m.accumulator_id,
        "home_team": m.home_team,
        "away_team": m.away_team,
        "prediction": m.prediction,
        "match_odds": float(m.match_odds),
        "analysis_text": m.analysis_text,
        "status": m.status,
    }

@router.get("/{accumulator_id}")
def get_matches(accumulator_id: str, db: Session = Depends(get_db), user=Depends(current_user)):
    acc = db.query(DailyAccumulator).filter(DailyAccumulator.id == accumulator_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Accumulator haipatikani")
    if not acc.is_visible and user.role != "admin":
        raise HTTPException(status_code=404, detail="Accumulator haipatikani")
    matches = db.query(IndividualMatch).filter(IndividualMatch.accumulator_id == accumulator_id).all()
    return [_serialize(m) for m in matches]

@router.post("")
def create_match(data: MatchCreate, db: Session = Depends(get_db), admin=Depends(admin_user)):
    acc = db.query(DailyAccumulator).filter(DailyAccumulator.id == data.accumulator_id).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Accumulator haipatikani")
    match = IndividualMatch(
        accumulator_id=data.accumulator_id,
        home_team=data.home_team,
        away_team=data.away_team,
        prediction=data.prediction,
        match_odds=data.match_odds,
        analysis_text=data.analysis_text,
        status=data.status,
    )
    db.add(match)
    db.commit()
    db.refresh(match)
    return _serialize(match)

@router.put("/{match_id}")
def update_match(match_id: str, data: MatchUpdate, db: Session = Depends(get_db), admin=Depends(admin_user)):
    match = db.query(IndividualMatch).filter(IndividualMatch.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Mechi haipatikani")
    if data.home_team is not None:
        match.home_team = data.home_team
    if data.away_team is not None:
        match.away_team = data.away_team
    if data.prediction is not None:
        match.prediction = data.prediction
    if data.match_odds is not None:
        match.match_odds = data.match_odds
    if data.analysis_text is not None:
        match.analysis_text = data.analysis_text
    if data.status is not None:
        match.status = data.status
    db.commit()
    db.refresh(match)
    return _serialize(match)

@router.delete("/{match_id}")
def delete_match(match_id: str, db: Session = Depends(get_db), admin=Depends(admin_user)):
    match = db.query(IndividualMatch).filter(IndividualMatch.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Mechi haipatikani")
    db.delete(match)
    db.commit()
    return {"message": "Mechi imefutwa"}