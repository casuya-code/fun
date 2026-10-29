from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, date, timedelta
from ..db import get_db
from ..deps import bearer
from ..auth import decode_token
from ..models import Visit, User

router = APIRouter()

def _client_ip(request: Request) -> str:
    """Real visitor IP, honouring a reverse proxy (nginx/Cloudflare)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = (request.headers.get("x-real-ip") or "").strip()
    if not ip:
        ip = request.client.host if request.client else "unknown"
    if ip.startswith("::ffff:"):
        ip = ip[7:]
    return ip or "unknown"

def _optional_user(creds=Depends(bearer), db: Session = Depends(get_db)):
    """Logged-in user if a valid token is present, otherwise None."""
    if not creds:
        return None
    data = decode_token(creds.credentials)
    if not data:
        return None
    return db.query(User).filter(User.id == data.get("sub")).first()

def record_visit(db: Session, ip: str, user_id: str = None):
    db.add(Visit(ip=ip, user_id=user_id))
    db.commit()

@router.post("/visits")
def create_visit(request: Request, db: Session = Depends(get_db), user=Depends(_optional_user)):
    # Anonymous hits are stored for reference but never shown in the counters.
    record_visit(db, _client_ip(request), user.id if user else None)
    return {"ok": True, "counted": bool(user)}

@router.get("/visitor-stats")
def visitor_stats(db: Session = Depends(get_db)):
    now = datetime.now()
    today = now.date()
    yesterday = today - timedelta(days=1)
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    # All visits are counted (both logged-in and anonymous); each visit adds one.
    def visit_count(start, end=None):
        q = (db.query(func.count(Visit.id))
               .filter(Visit.created_at >= datetime.combine(start, datetime.min.time())))
        if end:
            q = q.filter(Visit.created_at < datetime.combine(end, datetime.min.time()))
        return q.scalar() or 0

    return {
        "yesterday": visit_count(yesterday, today),
        "today": visit_count(today, today + timedelta(days=1)),
        "week": visit_count(week_start, today + timedelta(days=1)),
        "month": visit_count(month_start, today + timedelta(days=1)),
        "year": visit_count(year_start, today + timedelta(days=1)),
        "total": visit_count(date(2000, 1, 1)),
    }
