import os
from urllib.parse import urlsplit

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings


def _normalize_url(url: str) -> tuple[str, dict]:
    """Make any Postgres URL SQLAlchemy/psycopg2 friendly.

    Render (and Heroku-style hosts) hand out ``postgres://`` URLs, which
    SQLAlchemy does not understand. External Render database URLs also need
    TLS, while the internal ``dpg-...`` hostname does not.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]

    connect_args: dict = {}
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        host = ""
    # Render's *external* database hostname ends with .render.com; connections
    # to it must be encrypted. The internal hostname (dpg-xxxx-a) does not.
    if host.endswith(".render.com") and "sslmode=" not in url:
        connect_args["sslmode"] = "require"
    return url, connect_args


_database_url, _connect_args = _normalize_url(settings.database_url)

# Free Render instances are small; keep the pool modest so the database's
# connection limit is not exhausted (overridable through the environment).
_pool_size = int(os.getenv("DB_POOL_SIZE", "5"))
_max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "10"))
_pool_recycle = int(os.getenv("DB_POOL_RECYCLE", "300"))

engine = create_engine(
    _database_url,
    pool_pre_ping=True,
    pool_size=_pool_size,
    max_overflow=_max_overflow,
    pool_timeout=30,
    pool_recycle=_pool_recycle,
    connect_args=_connect_args,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
