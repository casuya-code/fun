import os
import threading
from datetime import datetime, timedelta, date
from urllib.parse import urlsplit
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, text
from apscheduler.schedulers.background import BackgroundScheduler
from .db import Base, engine, SessionLocal
from .models import User, Subscription, DailyAccumulator, IndividualMatch, Visit, EngineMatch, PasswordResetToken, AuditLog
from .auth import hash_password
from .config import settings

app = FastAPI(title="Betva Acca App")

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

def _origin_allowed(request: _Req, origin: str) -> bool:
    if origin in ALLOWED_ORIGINS:
        return True
    try:
        parts = urlsplit(origin)
    except ValueError:
        return False
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return False
    origin_host = parts.netloc.lower()
    host = (request.headers.get("host") or "").strip().lower()
    if host and origin_host == host:
        return True
    forwarded = (request.headers.get("x-forwarded-host") or "").split(",")[0].strip().lower()
    return bool(forwarded) and origin_host == forwarded

_rate: dict = {}
class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        ip = request.client.host if request.client else "unknown"
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            origin = request.headers.get("origin")
            if origin and not _origin_allowed(request, origin):
                return _JSONResponse({"detail": "Origin not allowed"}, status_code=403)
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        now = _t.time()
        window = 60
        is_auth = request.url.path.startswith("/api/auth")
        limit = 60 if is_auth else 300
        key = (ip, is_auth)
        bucket = _rate.setdefault(key, [])
        bucket[:] = [t for t in bucket if now - t < window]
        if len(bucket) >= limit:
            return _JSONResponse({"detail": "Too many requests"}, status_code=429)
        bucket.append(now)
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
        path = request.url.path.lower()
        if path == "/" or path.endswith(".html"):
            resp.headers["Cache-Control"] = "no-store, max-age=0"
        elif path.endswith(".js") or path.endswith(".css"):
            resp.headers["Cache-Control"] = "no-cache, must-revalidate"
        return resp

app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

# Routers
from .routers import auth, admin, accumulators, matches, subscriptions, engine as engine_router
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(accumulators.router, prefix="/api/accumulators", tags=["accumulators"])
app.include_router(matches.router, prefix="/api/matches", tags=["matches"])
app.include_router(subscriptions.router, prefix="/api/subscriptions", tags=["subscriptions"])
app.include_router(engine_router.router, prefix="/api/engine", tags=["engine"])

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    # Ensure performance indexes exist on existing databases
    try:
        with engine.connect() as _c:
            _c.execute(text("CREATE INDEX IF NOT EXISTS ix_engine_matches_home_away ON engine_matches(home_team, away_team)"))
            _c.execute(text("ALTER TABLE engine_matches ADD COLUMN IF NOT EXISTS used BOOLEAN DEFAULT FALSE"))
            _c.execute(text("ALTER TABLE engine_matches ADD COLUMN IF NOT EXISTS kickoff_at TIMESTAMP"))
            _c.execute(text("CREATE INDEX IF NOT EXISTS ix_visits_user_id ON visits(user_id)"))
            _c.commit()
    except Exception as e:
        print("index creation error", e)
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.role == "admin").first()
        if not admin and settings.admin_password:
            admin = User(
                phone_number=settings.admin_phone,
                password_hash=hash_password(settings.admin_password),
                role="admin",
            )
            db.add(admin)
            db.commit()
        elif not admin:
            print("ADMIN_PASSWORD is not set; no admin account was created.")
    finally:
        db.close()

    def run_ingest():
        from .scraper import ingest
        s = SessionLocal()
        try:
            ingest(s)
        except Exception as e:
            print("ingest error", e)
        finally:
            s.close()

    def run_settle():
        from .models import EngineMatch
        from .results import refresh_kickoffs
        s = SessionLocal()
        try:
            refresh_kickoffs(s, s.query(EngineMatch).filter(EngineMatch.kickoff_at.is_(None)).all())
        except Exception as e:
            print("settle error", e)
        finally:
            s.close()

    def run_expire_subscriptions():
        """Expire subscriptions every Sunday at 18:59:59."""
        from .models import Subscription
        s = SessionLocal()
        try:
            now = datetime.utcnow()
            expired = s.query(Subscription).filter(
                Subscription.status == "Hai",
                Subscription.expires_at <= now
            ).all()
            for sub in expired:
                sub.status = "Imeisha"
            s.commit()
            print(f"Expired {len(expired)} subscriptions")
        except Exception as e:
            print("expire error", e)
        finally:
            s.close()

    def run_sms_warning():
        """Send SMS warning every Saturday at 18:59."""
        from .models import Subscription, User
        s = SessionLocal()
        try:
            now = datetime.utcnow()
            # Find subscriptions expiring within 24 hours that haven't been warned
            warning_time = now + timedelta(hours=24)
            subs = s.query(Subscription).filter(
                Subscription.status == "Hai",
                Subscription.expires_at <= warning_time,
                Subscription.warning_sms_sent == False
            ).all()
            for sub in subs:
                user = s.query(User).filter(User.id == sub.user_id).first()
                if user:
                    # TODO: Send SMS via WEB SMS PUSH API
                    print(f"SMS warning to {user.phone_number}: subscription expires {sub.expires_at}")
                    sub.warning_sms_sent = True
            s.commit()
            print(f"Sent {len(subs)} SMS warnings")
        except Exception as e:
            print("sms warning error", e)
        finally:
            s.close()

    scheduler = BackgroundScheduler()
    scheduler.add_job(run_ingest, "interval", hours=6, id="footystats")
    scheduler.add_job(run_settle, "interval", minutes=30, id="settle")
    # Weekly expiration: Sunday 18:59:59
    scheduler.add_job(run_expire_subscriptions, "cron", day_of_week="sun", hour=18, minute=59, second=59, id="expire")
    # Saturday warning: Saturday 18:59:00
    scheduler.add_job(run_sms_warning, "cron", day_of_week="sat", hour=18, minute=59, second=0, id="sms_warning")
    scheduler.start()
    # initial run in background
    threading.Thread(target=run_ingest, daemon=True).start()
    threading.Thread(target=run_settle, daemon=True).start()

@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)

@app.get("/health")
def health():
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