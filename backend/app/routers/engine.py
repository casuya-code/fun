from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import EngineMatch
from ..deps import admin_user

router = APIRouter()

@router.get("/matches")
def list_engine_matches(db: Session = Depends(get_db), admin=Depends(admin_user)):
    matches = db.query(EngineMatch).order_by(EngineMatch.match_date.desc()).all()
    return [{
        "id": m.id,
        "home_team": m.home_team,
        "away_team": m.away_team,
        "match_date": m.match_date.isoformat(),
        "kickoff_at": m.kickoff_at.isoformat() if m.kickoff_at else None,
        "odds": float(m.odds),
        "over15_pct": float(m.over15_pct) if m.over15_pct is not None else None,
        "avg_goals": float(m.avg_goals) if m.avg_goals is not None else None,
        "league": m.league,
        "match_url": m.match_url,
        "used": m.used,
        "filter_type": m.filter_type,
    } for m in matches]

@router.post("/sync")
def sync_engine(db: Session = Depends(get_db), admin=Depends(admin_user)):
    from ..scraper import ingest_engine, fetch_matches
    matches = fetch_matches()
    n = ingest_engine(db, matches)
    total = db.query(EngineMatch).count()
    return {"imported": n, "total": total}