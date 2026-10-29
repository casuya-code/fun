"""ADM - private accumulator engine for the admin only.

Step 1 filter  : high-frequency Over 1.5 (free data)
Step 4 combiner: builds a 10+ odds accumulator + fractional Kelly stake

This router is guarded by admin_user on every endpoint. It is NEVER exposed
to normal users, and nothing here is published to them.
"""
import threading
from datetime import datetime, timedelta, date
from decimal import Decimal


def today_eat():
    """Return today's date in EAT (UTC+3), matching the kickoff times stored in DB."""
    return datetime.now().date()


def is_kickoff_today(kd):
    """Check if a kickoff datetime (naive, assumed EAT) falls on today's EAT date."""
    if kd is None:
        return False
    kd_date = (kd.kickoff_at or kd.match_date).date()
    return kd_date == today_eat()
from functools import wraps
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import admin_user
from ..models import EngineMatch, EngineSlip, EngineSlipLeg, User

router = APIRouter()

# --- Step 1 thresholds (league/team level Over 1.5 frequency) ---
OVER15_THRESHOLD = Decimal("78")   # minimum Over 1.5 % to be a candidate
DEFAULT_OVER15 = Decimal("78")     # fallback probability when % is missing

# --- Step 4 combiner targets ---
MIN_COMBINED = Decimal("10")       # target 10+ combined odds
MAX_LEGS = 20                      # engine-only cap (users stay at 5); chance 2 beyond 12 if needed
KELLY_FRACTION = Decimal("0.25")   # 1/4 Kelly (conservative)

# --- settlement throttling (the free source rate-limits us) ---
RECHECK_MINUTES = 45               # do not re-query the same match more often


class LegSettleIn(BaseModel):
    match_id: str
    outcome: str  # win / lose


class SlipCreateIn(BaseModel):
    match_ids: List[str]
    note: Optional[str] = None


# Only one slip may be assembled at a time. Two admins (or a double-submit)
# must never consume the same unused matches and create duplicate slips.
_slip_lock = threading.Lock()


def _one_at_a_time(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not _slip_lock.acquire(blocking=False):
            raise HTTPException(409, "Mkeka mwingine unaundwa sasa. Subiri sekunde chache kisha ujaribu tena.")
        try:
            return fn(*args, **kwargs)
        finally:
            _slip_lock.release()
    return wrapper


# ---------- helpers ----------

def _pct(m: EngineMatch) -> Decimal:
    return m.over15_pct if m.over15_pct is not None else DEFAULT_OVER15


def _combined(odds_list) -> Decimal:
    total = Decimal("1")
    for o in odds_list:
        total *= Decimal(str(o))
    return round(total, 3)


def _kelly(combined_odds: Decimal, win_prob: Decimal) -> Decimal:
    """Fractional Kelly stake as a fraction of bankroll.

    b = decimal odds - 1, p = estimated probability, q = 1 - p
    f* = (b*p - q) / b,  then scaled down to 1/4 Kelly and floored at 0.
    """
    b = combined_odds - 1
    if b <= 0 or win_prob <= 0 or win_prob >= 1:
        return Decimal("0")
    full = (b * win_prob - (1 - win_prob)) / b
    if full <= 0:
        return Decimal("0")
    return round(full * KELLY_FRACTION, 4)


def _serialize_slip(slip: EngineSlip) -> dict:
    return {
        "id": slip.id,
        "created_at": slip.created_at.isoformat() if slip.created_at else None,
        "combined_odds": float(slip.combined_odds),
        "win_prob": float(slip.win_prob) if slip.win_prob is not None else None,
        "kelly_stake": float(slip.kelly_stake) if slip.kelly_stake is not None else None,
        "status": slip.status,
        "note": slip.note,
        "legs": [
            {
                "match_id": leg.match_id,
                "home_team": leg.match.home_team if leg.match else "?",
                "away_team": leg.match.away_team if leg.match else "?",
                "over15_pct": float(leg.match.over15_pct) if leg.match and leg.match.over15_pct is not None else None,
                "odds": float(leg.odds),
                "outcome": leg.outcome,
                "score": f"{leg.home_goals}-{leg.away_goals}"
                          if leg.home_goals is not None and leg.away_goals is not None else None,
                "kickoff": leg.match.kickoff_at.isoformat() if leg.match and leg.match.kickoff_at else None,
            } for leg in slip.legs
        ],
    }


# ---------- automatic settlement ----------

def settle_pending(db, pause: float = 1.0, max_requests: int = 50) -> dict:
    """Look up final scores for every unsettled leg and settle what we can using AI + scraping."""
    import time as _time
    from datetime import timedelta
    from ..results import fetch_match_page
    from ..ai_results import ai_fetch_score

    slips = db.query(EngineSlip).filter(EngineSlip.status == "draft").all()
    if not slips:
        return {"matches_checked": 0, "legs_settled": 0, "slips_settled": 0, "note": "hakuna mikeka"}

    now = datetime.utcnow()
    # every leg that still needs a result
    pending = [l for s in slips for l in s.legs if not l.outcome and l.match]
    # candidates that have kicked off
    candidates = []
    for l in pending:
        m = l.match
        # fall back to the scheduled date when no real kickoff was found yet
        starts = m.kickoff_at or m.match_date
        if starts and starts > now:
            continue  # not started yet
        if m.last_checked_at and (now - m.last_checked_at) < timedelta(minutes=RECHECK_MINUTES):
            continue
        candidates.append(m)

    checked, settled_legs = set(), 0
    limited = False
    for m in candidates:
        if len(checked) >= max_requests:
            break
        if m.id in checked:
            continue
        checked.add(m.id)
        m.last_checked_at = now
        hg = ag = None
        status = None
        ko = None
        
        # Try footystats first if URL exists
        if m.match_url:
            try:
                status, hg, ag, ko = fetch_match_page(m.match_url)
            except Exception as e:
                if "429" in str(e) or "timed out" in str(e).lower():
                    limited = True
                # continue to AI fallback
        
        # If not found via footystats, use AI scraping
        if status != "finished" or hg is None or ag is None:
            try:
                ai_res = ai_fetch_score(m.home_team, m.away_team, m.match_date)
                if ai_res and ai_res.finished and ai_res.home_score is not None and ai_res.away_score is not None:
                    hg, ag = ai_res.home_score, ai_res.away_score
                    status = "finished"
                    print(f"AI settled {m.home_team} vs {m.away_team}: {hg}-{ag} via {ai_res.source}")
            except Exception as e:
                print(f"AI settlement error for {m.home_team} vs {m.away_team}: {e}")
        
        if ko and not m.kickoff_at:
            m.kickoff_at = ko
        if status == "finished" and hg is not None and ag is not None:
            for l in pending:
                if l.match_id == m.id and not l.outcome:
                    l.home_goals, l.away_goals = hg, ag
                    l.outcome = "win" if (hg + ag) >= 2 else "lose"
                    settled_legs += 1
        _time.sleep(pause)

    newly = 0
    for slip in slips:
        outcomes = [l.outcome for l in slip.legs]
        if outcomes and all(o in ("win", "lose") for o in outcomes):
            slip.status = "lost" if "lose" in outcomes else "won"
            newly += 1
    db.commit()
    note = "AI imetumia vyanzo mbadala" if settled_legs > 0 else None
    if limited and settled_legs == 0:
        note = "imepimwa mara nyingi (429) - AI inajaribu"
    return {"matches_checked": len(checked), "legs_settled": settled_legs,
            "slips_settled": newly, "note": note}


# ---------- Step 1: candidates ----------

@router.get("/candidates")
def candidates(min_over: float = float(OVER15_THRESHOLD), db: Session = Depends(get_db),
               user=Depends(admin_user)):
    """Matches that clear the Over 1.5 frequency filter, with the reason shown."""
    from datetime import datetime
    today = datetime.now().date()
    rows = db.query(EngineMatch).order_by(EngineMatch.match_date, EngineMatch.odds).all()
    out = []
    for m in rows:
        kd = m.kickoff_at or m.match_date
        # Only today's matches that have not started yet (never tomorrow's)
        if kd.date() != today:
            continue
        if kd <= datetime.now():
            continue
        p = _pct(m)
        qualifies = p >= Decimal(str(min_over))
        out.append({
            "id": m.id,
            "home_team": m.home_team,
            "away_team": m.away_team,
            "match_date": m.match_date.isoformat(),
            "kickoff": m.kickoff_at.isoformat() if m.kickoff_at else None,
            "odds": float(m.odds),
            "over15_pct": float(m.over15_pct) if m.over15_pct is not None else None,
            "avg_goals": float(m.avg_goals) if m.avg_goals is not None else None,
            "league": m.league or "-",
            "qualifies": qualifies,
            "used": bool(m.used),
            # human-readable explanation of WHY this is (or is not) a candidate
            "reason": f"Over 1.5 {p}% · wastani mabao {m.avg_goals if m.avg_goals is not None else '-'}",
        })
    return out


@router.post("/sync")
def sync(db: Session = Depends(get_db), user=Depends(admin_user)):
    """Re-scan the free source and refresh engine matches."""
    from ..scraper import ingest_engine
    try:
        added = ingest_engine(db)
        total = db.query(EngineMatch).count()
        return {"added": added, "total": total}
    except Exception as e:
        total = db.query(EngineMatch).count()
        raise HTTPException(503, f"Imeshindwa kusawazisha kutoka chanzo (403). Mechi zilizopo bado zipo: {total}. Jaribu tena baadaye au ongeza mechi wewe mwenyewe.")


# ---------- Step 4: combiner ----------

@router.post("/generate")
@_one_at_a_time
def generate(db: Session = Depends(get_db), user=Depends(admin_user)):
    """Auto-build one accumulator: 12-leg base, extend to 20 if odds stay under 10."""
    from datetime import datetime
    from sqlalchemy import or_
    now = datetime.now()
    today = now.date()
    # Allow another slip: it will consume only the remaining unused matches
    rows = (db.query(EngineMatch)
              .filter(
                  or_(EngineMatch.over15_pct >= OVER15_THRESHOLD,
                      EngineMatch.over15_pct.is_(None)),
                  EngineMatch.used == False,
              )
              .order_by(EngineMatch.odds.desc(), EngineMatch.over15_pct.desc())
              .all())
    # keep only today's upcoming (not started) matches - no jumping to next day
    upcoming = []
    for m in rows:
        kd = m.kickoff_at or m.match_date
        if kd and kd <= now:
            continue
        # the real kickoff wins: a match listed for today but played tomorrow
        # (or the reverse) must follow its kickoff date, not the scrape date
        if kd.date() != today:
            continue
        upcoming.append(m)
    if len(upcoming) < 2:
        raise HTTPException(400, "Hakuna mechi za kutosha (angalau 2 zenye Over 1.5 juu ya 78%)")

    legs, used_teams, used_ids = [], set(), set()

    def _try_add(m):
        if len(legs) >= MAX_LEGS or m.id in used_ids:
            return False
        teams = {m.home_team.strip().lower(), m.away_team.strip().lower()}
        if used_teams & teams:
            return False  # avoid duplicate teams
        used_teams.update(teams)
        used_ids.add(m.id)
        legs.append(m)
        return True

    # Base attempt: 12 legs (or every available match if fewer)
    for m in upcoming:
        if len(legs) >= 12:
            break
        _try_add(m)

    if len(legs) < 2:
        raise HTTPException(400, "Hakuna mechi 2 tofauti za kutosha (timu zinarudia)")

    combined = _combined([m.odds for m in legs])

    # Chance 2: extend up to 20 legs only when the base is still below 10
    if combined < MIN_COMBINED:
        for m in upcoming:
            if len(legs) >= MAX_LEGS or combined >= MIN_COMBINED:
                break
            _try_add(m)
            combined = _combined([m.odds for m in legs])

    note = "Otomatiki (Step 1 + Step 4)"
    if len(legs) > 12 and combined >= MIN_COMBINED:
        note = f"Otomatiki (Option 2: {len(legs)} legs, odds {combined})"
    elif combined < MIN_COMBINED:
        # Option 3: create with whatever odds are available
        note = f"Otomatiki (Option 3: odds {combined} < {MIN_COMBINED})"

    win_prob = Decimal("1")
    for m in legs:
        win_prob *= _pct(m) / Decimal("100")
    win_prob = round(win_prob, 4)

    slip = EngineSlip(
        created_by=user.id,
        combined_odds=combined,
        win_prob=win_prob,
        kelly_stake=_kelly(combined, win_prob),
        status="draft",
        note=note,
    )
    db.add(slip)
    db.flush()
    for m in legs:
        db.add(EngineSlipLeg(slip_id=slip.id, match_id=m.id, odds=m.odds))
        m.used = True
    db.commit()
    db.refresh(slip)
    return _serialize_slip(slip)


@router.post("/slips")
@_one_at_a_time
def create_slip(data: SlipCreateIn, db: Session = Depends(get_db), user=Depends(admin_user)):
    """Manually assemble a slip from chosen matches."""
    if not data.match_ids or len(data.match_ids) > MAX_LEGS:
        raise HTTPException(400, f"Chagua 1 hadi {MAX_LEGS} mechi")
    if len(set(data.match_ids)) != len(data.match_ids):
        raise HTTPException(400, "Mechi kurudia")
    matches = db.query(EngineMatch).filter(EngineMatch.id.in_(data.match_ids)).all()
    if len(matches) != len(set(data.match_ids)):
        raise HTTPException(400, "Baadhi ya mechi hazipatikani")
    # only today's not-yet-started matches that have not been used in another slip
    from datetime import datetime
    now = datetime.now()
    today = now.date()
    teams = set()
    for m in matches:
        if m.used:
            raise HTTPException(400, f"Mechi tayari imetumika: {m.home_team} / {m.away_team}")
        kd = m.kickoff_at or m.match_date
        if kd <= datetime.now():
            raise HTTPException(400, f"Mechi tayari imeanza: {m.home_team} / {m.away_team}")
        if kd.date() != today:
            raise HTTPException(400, f"Mechi si ya leo: {m.home_team} / {m.away_team}")
        t = {m.home_team.strip().lower(), m.away_team.strip().lower()}
        if teams & t:
            raise HTTPException(400, f"Timu inarudia: {m.home_team} / {m.away_team}")
        teams |= t

    combined = _combined([m.odds for m in matches])
    note = data.note
    if combined < MIN_COMBINED:
        note = f"Mkeka wa mkono (odds {combined} < {MIN_COMBINED})"

    win_prob = Decimal("1")
    for m in matches:
        win_prob *= _pct(m) / Decimal("100")
    win_prob = round(win_prob, 4)

    slip = EngineSlip(created_by=user.id, combined_odds=combined, win_prob=win_prob,
                      kelly_stake=_kelly(combined, win_prob), status="draft", note=note)
    db.add(slip)
    db.flush()
    for m in matches:
        db.add(EngineSlipLeg(slip_id=slip.id, match_id=m.id, odds=m.odds))
        m.used = True
    db.commit()
    db.refresh(slip)
    return _serialize_slip(slip)


@router.post("/settle")
def settle_now(db: Session = Depends(get_db), user=Depends(admin_user)):
    """Fetch final scores now and settle whatever has finished using AI."""
    return settle_pending(db)


@router.post("/settle/ai")
def settle_now_ai(db: Session = Depends(get_db), user=Depends(admin_user)):
    """Force AI settlement for all pending matches."""
    return settle_pending(db)


@router.get("/slips")
def list_slips(db: Session = Depends(get_db), user=Depends(admin_user)):
    slips = (db.query(EngineSlip)
               .filter(EngineSlip.status != "archived")
               .order_by(EngineSlip.created_at.desc()).all())
    return [_serialize_slip(s) for s in slips]


@router.post("/archive")
def archive_settled(db: Session = Depends(get_db), user=Depends(admin_user)):
    """Hide completed slips from the working list (keeps them for history)."""
    q = db.query(EngineSlip).filter(EngineSlip.status.in_(("won", "lost")))
    n = q.update({"status": "archived"}, synchronize_session=False)
    db.commit()
    return {"archived": n}


@router.post("/slips/{slip_id}/settle")
def settle_slip(slip_id: str, legs: List[LegSettleIn], db: Session = Depends(get_db),
                user=Depends(admin_user)):
    """Record results for each leg, then compute the slip result."""
    slip = db.query(EngineSlip).filter(EngineSlip.id == slip_id).first()
    if not slip:
        raise HTTPException(404, "Hakupatikani")
    by_match = {l.match_id: l for l in legs}
    for leg in slip.legs:
        req = by_match.get(leg.match_id)
        if req:
            if req.outcome not in ("win", "lose"):
                raise HTTPException(400, "Matokeo yanapaswa kuwa win au lose")
            leg.outcome = req.outcome
            # For Over 1.5, if win we need at least 2 goals total
            if req.outcome == "win" and leg.home_goals is None:
                leg.home_goals = 1
                leg.away_goals = 1
            elif req.outcome == "lose" and leg.home_goals is None:
                leg.home_goals = 0
                leg.away_goals = 0
    outcomes = [l.outcome for l in slip.legs]
    if all(o in ("win", "lose") for o in outcomes):
        slip.status = "lost" if "lose" in outcomes else "won"
    db.commit()
    db.refresh(slip)
    return _serialize_slip(slip)


# ---------- learn the trends ----------

@router.get("/stats")
def stats(db: Session = Depends(get_db), user=Depends(admin_user)):
    slips = db.query(EngineSlip).filter(EngineSlip.status != "archived").all()
    total = len(slips)
    won = len([s for s in slips if s.status == "won"])
    lost = len([s for s in slips if s.status == "lost"])
    settled = won + lost
    stake = settled  # 1 unit staked per settled slip
    returns = sum(float(s.combined_odds) for s in slips if s.status == "won")
    roi = round((returns - stake) / stake * 100, 1) if stake else None

    # per-filter breakdown (which leg type is actually winning)
    per_filter = {}
    for s in slips:
        for leg in s.legs:
            ft = leg.match.filter_type if leg.match else "over15"
            d = per_filter.setdefault(ft, {"win": 0, "lose": 0})
            if leg.outcome in ("win", "lose"):
                d[leg.outcome] += 1
    for ft, d in per_filter.items():
        tot = d["win"] + d["lose"]
        d["win_rate"] = round(d["win"] / tot * 100, 1) if tot else None
        d["total"] = tot

    return {
        "slips": total,
        "won": won,
        "lost": lost,
        "pending": total - settled,
        "win_rate": round(won / settled * 100, 1) if settled else None,
        "roi_pct": roi,
        "avg_odds": round(sum(float(s.combined_odds) for s in slips) / total, 2) if total else None,
        "per_filter": per_filter,
    }
