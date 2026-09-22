import os
import ssl
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from backend.app.core.config import settings

# Load database URL exclusively from environment or fallback to local SQLite for dev
raw_url = settings.DATABASE_URL or os.environ.get("DATABASE_URL") or "sqlite:///./backend/data/confit.db"



def _postgres_driver_available(name: str) -> bool:
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def normalise_postgres_url(url: str):
    """Return (sqlalchemy_url, connect_args) for a PostgreSQL DSN.

    Driver selection is DETERMINISTIC and based on what is installed, not on
    whether the operator happened to append ``sslmode=`` to the DSN:

      * Vercel installs only ``pg8000`` (requirements.txt: no C extensions), so
        a plain ``postgresql://`` DSN must still use pg8000 — previously it
        selected the psycopg2 dialect and the function crashed at import.
      * Docker/CI (backend/requirements.txt) has psycopg2, which understands
        ``sslmode`` natively.

    With pg8000 the libpq-only ``sslmode`` query parameter is stripped and
    translated into an SSL context (``sslmode=disable`` -> no TLS).
    """
    url = url.replace("postgres://", "postgresql://", 1)
    explicit_driver = url.startswith("postgresql+")
    if explicit_driver:
        driver = url.split("+", 1)[1].split("://", 1)[0]
    elif _postgres_driver_available("psycopg2"):
        driver = "psycopg2"
    elif _postgres_driver_available("pg8000"):
        driver = "pg8000"
    else:
        raise RuntimeError(
            "DATABASE_URL is PostgreSQL but neither psycopg2 nor pg8000 is installed "
            "(Vercel manifest requirements.txt provides pg8000; backend/requirements.txt provides psycopg2)"
        )
    args = {}
    if driver == "pg8000":
        base, _, query = url.partition("?")
        params = [kv for kv in query.split("&") if kv]
        sslmode = None
        kept = []
        for kv in params:
            k, _, v = kv.partition("=")
            if k == "sslmode":
                sslmode = v
            elif k in ("channel_binding",):
                continue  # libpq-only
            else:
                kept.append(kv)
        url = base + ("?" + "&".join(kept) if kept else "")
        if not url.startswith("postgresql+pg8000://"):
            url = url.replace("postgresql://", "postgresql+pg8000://", 1)
        if sslmode != "disable":
            args = {"ssl_context": ssl.create_default_context()}
    return url, args


connect_args = {}
if "postgres" in raw_url:
    raw_url, connect_args = normalise_postgres_url(raw_url)
elif "sqlite" in raw_url:
    connect_args = {"check_same_thread": False}
    try:
        sqlite_path = raw_url.replace("sqlite:///", "")
        dir_name = os.path.dirname(sqlite_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
    except Exception:
        pass

# pool_pre_ping issues a liveness round trip (effectively `SELECT 1`) EVERY time
# a connection is checked out of the pool. That is the correct default when a
# process holds long-lived connections that a proxy or the database may have
# closed underneath it -- reconnecting transparently beats surfacing a stale
# socket as a 500.
#
# Measured against the production database it costs ~150ms per checkout, and in
# the serverless deployment a request typically checks out once, so every single
# API call pays a full extra round trip before it does any work.
#
# The trade is only safe to take where something else already guarantees the
# connection is fresh. On serverless the function is short-lived and pooled
# behind Neon's own connection pooler, and pool_recycle below already discards
# connections older than the proxy's idle timeout, so the pre-ping is redundant
# there. On a long-running server (local dev, the Docker image) it is NOT
# redundant, so it stays on. Overridable via DB_POOL_PRE_PING for operators who
# hit stale-connection errors and want the check back unconditionally.
_is_serverless = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
_pre_ping_env = os.getenv("DB_POOL_PRE_PING")
if _pre_ping_env is not None:
    _pre_ping = _pre_ping_env.strip().lower() in ("1", "true", "yes", "on")
else:
    _pre_ping = not _is_serverless

engine = create_engine(
    raw_url,
    connect_args=connect_args,
    pool_pre_ping=_pre_ping,
    pool_recycle=300,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
