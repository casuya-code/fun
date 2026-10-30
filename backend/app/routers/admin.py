import time as _time
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, time
from ..db import get_db
from ..models import Prediction, User, EngineMatch
from ..schemas import PredictionCreate, PredictionUpdate, AllowIn
from ..deps import admin_user
from ..scraper import ingest
from ..results import fetch_match_page
from ..ai_results import ai_fetch_score


class PredictionSettleIn(BaseModel):
    outcome: str  # win / lose


class PredictionSettleBulkItem(BaseModel):
    prediction_id: str
    outcome: str  # win / lose


class PredictionSettleBulkIn(BaseModel):
    items: List[PredictionSettleBulkItem]

router = APIRouter()

# settlement throttling (the free source rate-limits us)
RECHECK_MINUTES = 45

def serialize(p):
    return {
        "id": p.id,
        "home_team": p.home_team,
        "away_team": p.away_team,
        "match_date": p.match_date.isoformat(),
        "odds": float(p.odds),
        "status": p.status,
        "outcome": p.outcome,
        "home_goals": p.home_goals,
        "away_goals": p.away_goals,
        "score": (f"{p.home_goals}-{p.away_goals}"
                  if p.home_goals is not None and p.away_goals is not None else None),
        "allowed": p.allowed,
        "allowed_at": p.allowed_at.isoformat() if p.allowed_at else None,
        "locked": bool(p.allowed and p.allowed_at and (datetime.utcnow() - p.allowed_at).total_seconds() > 300),
    }

@router.get("/predictions")
def list_predictions(db: Session = Depends(get_db), admin=Depends(admin_user)):
    preds = db.query(Prediction).order_by(Prediction.match_date.desc()).all()
    return [serialize(p) for p in preds]

@router.post("/predictions")
def create_prediction(data: PredictionCreate, db: Session = Depends(get_db), admin=Depends(admin_user)):
    p = Prediction(
        home_team=data.home_team,
        away_team=data.away_team,
        match_date=data.match_date,
        odds=data.odds,
        status="scheduled",
        allowed=False,
        created_by=admin.id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return serialize(p)

@router.put("/predictions/{pred_id}")
def update_prediction(pred_id: str, data: PredictionUpdate, db: Session = Depends(get_db), admin=Depends(admin_user)):
    p = db.query(Prediction).filter(Prediction.id == pred_id).first()
    if not p:
        raise HTTPException(404, "Hakupatikani")
    if data.home_team is not None: p.home_team = data.home_team
    if data.away_team is not None: p.away_team = data.away_team
    if data.match_date is not None: p.match_date = data.match_date
    if data.odds is not None: p.odds = data.odds
    if data.status is not None: p.status = data.status
    if data.outcome is not None: p.outcome = data.outcome
    db.commit()
    db.refresh(p)
    return serialize(p)

@router.post("/predictions/{pred_id}/allow")
def allow_prediction(pred_id: str, data: AllowIn, db: Session = Depends(get_db), admin=Depends(admin_user)):
    p = db.query(Prediction).filter(Prediction.id == pred_id).first()
    if not p:
        raise HTTPException(404, "Hakupatikani")
    if data.allowed is False and p.allowed and p.allowed_at:
        if (datetime.now() - p.allowed_at).total_seconds() > 300:
            raise HTTPException(400, "Haiwezi kubadilishwa baada ya dakika 5")
    p.allowed = data.allowed
    if data.allowed:
        p.allowed_at = datetime.now()
    else:
        p.allowed_at = None
    db.commit()
    db.refresh(p)
    return serialize(p)

@router.post("/sync-footystats")
def sync_footystats(db: Session = Depends(get_db), admin=Depends(admin_user)):
    n = ingest(db)
    return {"imported": n}

@router.get("/users")
def list_users(db: Session = Depends(get_db), admin=Depends(admin_user)):
    users = db.query(User).all()
    return [{"id": u.id, "email": u.email, "nickname": u.nickname, "role": u.role, "created_at": u.created_at.isoformat()} for u in users]


# ---------- settlement of finished matches ----------

def settle_predictions(db, pause: float = 2.5, max_requests: int = 12) -> dict:
    """Fetch final scores for every unsettled prediction whose match has started.

    A prediction is Over 1.5, so it wins when the match produced 2+ goals.
    Matches that have not finished are left pending - never guessed.

    The free source rate-limits us, so: only matches whose kickoff has passed
    are queried, each match is re-checked at most once per RECHECK_MINUTES,
    and the sweep stops early on a rate-limit response.
    """
    now = datetime.now()
    pending = [p for p in db.query(Prediction).filter(Prediction.outcome.is_(None)).all()]
    if not pending:
        return {"checked": 0, "settled": 0, "note": "hakuna mechi zinazosubiri"}

    # pair each prediction with its engine row (carries the result page URL)
    candidates = []
    for p in pending:
        # match by teams and same day: the prediction's match_date is replaced
        # with the real kickoff, while the engine row keeps the 12:00 placeholder
        day_start = datetime.combine(p.match_date.date(), time.min)
        day_end = day_start + timedelta(days=1)
        m = (db.query(EngineMatch)
               .filter(EngineMatch.home_team == p.home_team,
                       EngineMatch.away_team == p.away_team,
                       EngineMatch.match_date >= day_start,
                       EngineMatch.match_date < day_end)
               .first())
        # allow AI fallback even when no engine match / url exists
        if p.match_date and p.match_date > now:
            continue  # scheduled for a later day - nothing to look up yet
        if m and m.kickoff_at and m.kickoff_at > now:
            continue  # not started yet
        if m and m.last_checked_at and (now - m.last_checked_at) < timedelta(minutes=RECHECK_MINUTES):
            continue
        candidates.append((p, m))

    checked, settled, limited = set(), 0, False
    for p, m in candidates:
        match_key = m.id if m else p.id
        if len(checked) >= max_requests:
            break
        if match_key in checked:
            continue
        checked.add(match_key)
        if m:
            m.last_checked_at = now
        status = None
        hg = ag = None
        ko = None
        # 1) footystats page
        if m and m.match_url:
            try:
                status, hg, ag, ko = fetch_match_page(
                    m.match_url, p.home_team, p.away_team, p.match_date)
            except Exception as e:
                msg = str(e).lower()
                if "429" in msg or "timed out" in msg or "connection" in msg or "reset" in msg:
                    limited = True
                # fall through to AI
        # 2) AI fallback (scraping). A postponed page has no score to find.
        if status != "postponed" and (status != "finished" or hg is None or ag is None):
            try:
                ai_res = ai_fetch_score(p.home_team, p.away_team, p.match_date)
                if ai_res and ai_res.finished and ai_res.home_score is not None and ai_res.away_score is not None:
                    hg, ag = ai_res.home_score, ai_res.away_score
                    status = "finished"
                    print(f"AI settled {p.home_team} vs {p.away_team}: {hg}-{ag} via {ai_res.source}")
            except Exception as e:
                print(f"AI settlement error for {p.home_team} vs {p.away_team}: {e}")
        if ko and m and not m.kickoff_at:
            m.kickoff_at = ko
        if status == "finished" and hg is not None and ag is not None:
            p.outcome = "win" if (hg + ag) >= 2 else "lose"
            p.status = "finished"
            p.home_goals, p.away_goals = int(hg), int(ag)
            settled += 1
        _time.sleep(pause)

    db.commit()
    note = "imepimwa mara nyingi (429) - itaendelea baadae" if limited else None
    return {"checked": len(checked), "settled": settled, "note": note}


@router.post("/settle")
def settle_now(db: Session = Depends(get_db), admin=Depends(admin_user)):
    """Fetch final scores now and settle every prediction that has finished."""
    return settle_predictions(db, pause=1.5, max_requests=40)


@router.put("/predictions/{pred_id}/settle")
def settle_prediction_manual(pred_id: str, data: PredictionSettleIn, db: Session = Depends(get_db), admin=Depends(admin_user)):
    """Manually settle a single prediction (useful when automatic scraping can't find the result)."""
    p = db.query(Prediction).filter(Prediction.id == pred_id).first()
    if not p:
        raise HTTPException(404, "Hakupatikani")
    if data.outcome not in ("win", "lose"):
        raise HTTPException(400, "Matokeo yanapaswa kuwa win au lose")
    p.outcome = data.outcome
    p.status = "finished"
    db.commit()
    db.refresh(p)
    return serialize(p)


@router.post("/predictions/settle")
def settle_predictions_bulk(data: PredictionSettleBulkIn, db: Session = Depends(get_db), admin=Depends(admin_user)):
    """Manually settle multiple predictions at once."""
    # Validate every outcome before touching any row, so one bad item cannot
    # leave the batch half-applied.
    for item in data.items:
        if item.outcome not in ("win", "lose"):
            raise HTTPException(400, "Matokeo yanapaswa kuwa win au lose")
    count = 0
    for item in data.items:
        p = db.query(Prediction).filter(Prediction.id == item.prediction_id).first()
        if not p:
            continue
        p.outcome = item.outcome
        p.status = "finished"
        count += 1
    db.commit()
    return {"settled": count}


# ---------- per-day history (single + accumulator) ----------

@router.get("/history")
def history(db: Session = Depends(get_db), admin=Depends(admin_user)):
    """All admin matches grouped by day.

    Each match carries its own (single) outcome; each day is also graded as an
    accumulator - a day only wins when every match that day won.
    """
    preds = db.query(Prediction).order_by(Prediction.match_date, Prediction.odds).all()
    days = {}
    for p in preds:
        key = p.match_date.date().isoformat()
        day = days.setdefault(key, {"date": key, "matches": [], "won": 0, "lose": 0, "pending": 0})
        outcome = p.outcome if p.outcome in ("win", "lose") else None
        if outcome == "win":
            day["won"] += 1
        elif outcome == "lose":
            day["lose"] += 1
        else:
            day["pending"] += 1
        day["matches"].append({
            "id": p.id,
            "home_team": p.home_team,
            "away_team": p.away_team,
            "match_date": p.match_date.isoformat(),
            "odds": float(p.odds),
            "status": p.status,
            "outcome": outcome,
        })

    out = []
    for key in sorted(days, reverse=True):
        day = days[key]
        settled = day["won"] + day["lose"]
        # accumulator grade: all settled matches must win, and none may lose
        if day["lose"] > 0:
            acca = "lose"
        elif settled == 0 or day["pending"] > 0:
            acca = "pending"
        else:
            acca = "win"
        day["acca"] = acca
        day["total"] = settled + day["pending"]
        day["hit_rate"] = round(day["won"] / settled * 100, 1) if settled else None
        out.append(day)
    return out

@router.post("/refresh-kickoffs")
def refresh_kickoffs_endpoint(db: Session = Depends(get_db), admin=Depends(admin_user)):
    """Manually refresh kickoff times for all matches using API-Football."""
    try:
        from .scraper import _fetch_kickoff_for_match
        from ..models import EngineMatch, Prediction
        from datetime import datetime, timedelta, time
        from ..config import settings

        has_key = bool(settings.football_api_key)
        engine_matches = db.query(EngineMatch).filter(EngineMatch.kickoff_at.is_(None)).all()
        updated = 0
        errors = []
        for m in engine_matches:
            try:
                ko = _fetch_kickoff_for_match(m.home_team, m.away_team, m.match_date)
                if ko:
                    m.kickoff_at = ko
                    m.match_date = ko
                    db.query(Prediction).filter(
                        Prediction.home_team == m.home_team,
                        Prediction.away_team == m.away_team,
                    ).update({"match_date": ko}, synchronize_session=False)
                    db.commit()
                    updated += 1
                else:
                    errors.append(f"{m.home_team} vs {m.away_team}".encode("ascii", "replace").decode())
            except Exception as e:
                errors.append(f"ERR: {str(e)}".encode("ascii", "replace").decode())
        return {"has_football_api_key": has_key, "engine_matches_without_kickoff": len(engine_matches), "updated": updated, "not_found": errors[:10]}
    except Exception as e:
        return {"error": str(e).encode("ascii", "replace").decode()}
