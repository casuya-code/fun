from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from ..db import get_db
from ..models import User, UserPick, UserPickLeg, Follow, Prediction
from ..deps import current_user

router = APIRouter()

def user_stats(db, user):
    picks = db.query(UserPick).filter(UserPick.user_id == user.id).all()
    single_won = single_lost = 0
    combined_won = combined_lost = 0
    STAKE = 10000.0
    single_profit = 0.0
    combined_profit = 0.0
    for pk in picks:
        legs = pk.legs
        n = len(legs)
        outcomes = [l.prediction.outcome for l in legs]
        status = "pending"
        if any(o == "lose" for o in outcomes):
            status = "lost"
        elif outcomes and all(o == "win" for o in outcomes):
            status = "won"
        odds = float(pk.combined_odds)
        if status == "won":
            profit = (odds - 1.0) * STAKE
        elif status == "lost":
            profit = -STAKE
        else:
            profit = 0.0
        if n == 1:
            if status == "won": single_won += 1
            elif status == "lost": single_lost += 1
            single_profit += profit
        else:
            if status == "won": combined_won += 1
            elif status == "lost": combined_lost += 1
            combined_profit += profit
    return {
        "single_won": single_won,
        "single_lost": single_lost,
        "single_profit": round(single_profit, 2),
        "combined_won": combined_won,
        "combined_lost": combined_lost,
        "combined_profit": round(combined_profit, 2),
    }

def serialize_pick(pk):
    return {
        "id": pk.id,
        "created_at": pk.created_at.isoformat(),
        "combined_odds": float(pk.combined_odds),
        "status": "lost" if any(l.prediction.outcome == "lose" for l in pk.legs) else ("won" if pk.legs and all(l.prediction.outcome == "win" for l in pk.legs) else "pending"),
        "legs": [
            {"home_team": l.prediction.home_team, "away_team": l.prediction.away_team, "match_date": l.prediction.match_date.isoformat(), "odds": float(l.odds), "outcome": l.prediction.outcome} for l in pk.legs
        ],
    }

@router.get("")
def list_experts(db: Session = Depends(get_db), user=Depends(current_user)):
    users = db.query(User).filter(User.role == "user").all()
    following_ids = {f.following_id for f in db.query(Follow).filter(Follow.follower_id == user.id).all()}
    follow_count = len(following_ids)
    result = []
    for u in users:
        if u.id == user.id:
            continue
        stats = user_stats(db, u)
        is_following = u.id in following_ids
        can_follow = (not is_following) and (follow_count < 2)
        result.append({
            "id": u.id,
            "nickname": u.nickname,
            "role": u.role,
            **stats,
            "is_following": is_following,
            "can_follow": can_follow,
        })
    return result

@router.get("/{user_id}/picks")
def expert_picks(user_id: str, date: str = Query(default=None), db: Session = Depends(get_db), user=Depends(current_user)):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(404, "Mtumiaji hapatikani")
    # permission: self, admin, or follower
    if user.id != user_id and user.role != "admin":
        is_follower = db.query(Follow).filter(Follow.follower_id == user.id, Follow.following_id == user_id).first() is not None
        if not is_follower:
            raise HTTPException(403, "Mfuatie mtumiaji huyu kuona machaguo yake")
    from datetime import datetime, timedelta
    if date:
        try:
            d = datetime.strptime(date, "%Y-%m-%d").date()
        except Exception:
            d = datetime.utcnow().date()
    else:
        d = datetime.utcnow().date()
    start = datetime.combine(d, datetime.min.time())
    end = start + timedelta(days=1)
    # show picks that contain a match played on the requested day, not merely
    # picks that happened to be created that day
    picks = (db.query(UserPick)
               .join(UserPickLeg, UserPickLeg.pick_id == UserPick.id)
               .join(Prediction, Prediction.id == UserPickLeg.prediction_id)
               .filter(UserPick.user_id == user_id,
                       Prediction.match_date >= start,
                       Prediction.match_date < end)
               .distinct()
               .order_by(UserPick.created_at.desc())
               .all())
    return [serialize_pick(p) for p in picks]