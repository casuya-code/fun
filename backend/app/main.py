import os
import threading
from datetime import datetime, timedelta, date
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func
from apscheduler.schedulers.background import BackgroundScheduler
from .db import Base, engine, SessionLocal
from .models import User, Visit
from .auth import hash_password
from .config import settings
from .scraper import ingest

app = FastAPI(title="BetPicks")

import os
_allowed = os.getenv("ALLOWED_ORIGINS", "http://127.0.0.1:8000,http://localhost:8000")
ALLOWED_ORIGINS = [o.strip() for o in _allowed.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as _Req
from starlette.responses import JSONResponse as _JSONResponse
import time as _t

_rate: dict = {}
class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        ip = request.client.host if request.client else "unknown"
        # Origin check for state-changing API requests
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            origin = request.headers.get("origin")
            if origin and origin not in ALLOWED_ORIGINS:
                return _JSONResponse({"detail": "Origin not allowed"}, status_code=403)
        # Only API traffic is rate-limited; static files are served normally.
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        now = _t.time()
        window = 60
        is_auth = request.url.path.startswith("/api/auth")
        limit = 60 if is_auth else 300
        key = (ip, is_auth)
        bucket = _rate.setdefault(key, [])
        # drop old
        bucket[:] = [t for t in bucket if now - t < window]
        if len(bucket) >= limit:
            return _JSONResponse({"detail": "Too many requests"}, status_code=429)
        bucket.append(now)
        # keep the in-memory table from growing forever
        if len(_rate) > 5000:
            for k in [k for k, v in _rate.items() if not v]:
                _rate.pop(k, None)
        resp = await call_next(request)
        return resp

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        resp.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        resp.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'"
        # Always serve fresh HTML/JS/CSS so UI fixes are picked up immediately.
        path = request.url.path.lower()
        if path == "/" or path.endswith(".html"):
            resp.headers["Cache-Control"] = "no-store, max-age=0"
        elif path.endswith(".js") or path.endswith(".css"):
            resp.headers["Cache-Control"] = "no-cache, must-revalidate"
        return resp

app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

# Routers
from .routers import auth, admin, predictions, picks, experts, follows, stats, visits, adm
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(predictions.router, prefix="/api/predictions", tags=["predictions"])
app.include_router(picks.router, prefix="/api/picks", tags=["picks"])
app.include_router(experts.router, prefix="/api/experts", tags=["experts"])
app.include_router(follows.router, prefix="/api/follows", tags=["follows"])
app.include_router(stats.router, prefix="/api", tags=["stats"])
app.include_router(visits.router, prefix="/api", tags=["visits"])
app.include_router(adm.router, prefix="/api/adm", tags=["adm"])

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    # Ensure performance indexes exist on existing databases
    try:
        from sqlalchemy import text
        with engine.connect() as _c:
            _c.execute(text("CREATE INDEX IF NOT EXISTS ix_engine_slip_legs_match_id ON engine_slip_legs(match_id)"))
            _c.execute(text("CREATE INDEX IF NOT EXISTS ix_engine_matches_home_away ON engine_matches(home_team, away_team)"))
            _c.execute(text("CREATE INDEX IF NOT EXISTS ix_predictions_home_away ON predictions(home_team, away_team)"))
            _c.execute(text("CREATE INDEX IF NOT EXISTS ix_engine_matches_kickoff ON engine_matches(kickoff_at)"))
            _c.execute(text("ALTER TABLE engine_matches ADD COLUMN IF NOT EXISTS used BOOLEAN DEFAULT FALSE"))
            _c.execute(text("ALTER TABLE visits ADD COLUMN IF NOT EXISTS user_id VARCHAR"))
            _c.execute(text("ALTER TABLE predictions ADD COLUMN IF NOT EXISTS home_goals INTEGER"))
            _c.execute(text("ALTER TABLE predictions ADD COLUMN IF NOT EXISTS away_goals INTEGER"))
            _c.execute(text("CREATE INDEX IF NOT EXISTS ix_visits_user_id ON visits(user_id)"))
            _c.commit()
    except Exception as e:
        print("index creation error", e)
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == settings.admin_email).first()
        if not admin and settings.admin_password:
            admin = User(
                email=settings.admin_email,
                password_hash=hash_password(settings.admin_password),
                nickname=settings.admin_nickname,
                role="admin",
            )
            db.add(admin)
            db.commit()
        elif not admin:
            print("ADMIN_PASSWORD is not set; no admin account was created.")
    finally:
        db.close()

    def run_ingest():
        s = SessionLocal()
        try:
            ingest(s)
        except Exception as e:
            print("ingest error", e)
        finally:
            s.close()

    def run_settle():
        """Auto-settle ADM slips and fill in real kickoff times."""
        from .routers.adm import settle_pending
        from .routers.admin import settle_predictions
        from .models import EngineMatch
        from .results import refresh_kickoffs
        s = SessionLocal()
        try:
            refresh_kickoffs(s, s.query(EngineMatch).filter(EngineMatch.kickoff_at.is_(None)).all())
            settle_pending(s)
            settle_predictions(s)
        except Exception as e:
            print("settle error", e)
        finally:
            s.close()

    scheduler = BackgroundScheduler()
    scheduler.add_job(run_ingest, "interval", hours=6, id="footystats")
    scheduler.add_job(run_settle, "interval", minutes=30, id="settle")
    scheduler.start()
    # initial run in background
    threading.Thread(target=run_ingest, daemon=True).start()
    threading.Thread(target=run_settle, daemon=True).start()

@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)

@app.get("/health")
def health():
    """Liveness probe: 200 when the API and database are reachable."""
    from sqlalchemy import text as _text
    try:
        with engine.connect() as c:
            c.execute(_text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    body = '{"status":"ok","db":true}' if db_ok else '{"status":"degraded","db":false}'
    return Response(content=body, status_code=200 if db_ok else 503, media_type="application/json")

frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")