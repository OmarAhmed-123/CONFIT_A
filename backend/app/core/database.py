import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from backend.app.core.config import settings

# Load database URL exclusively from environment or fallback to local SQLite for dev
raw_url = settings.DATABASE_URL or os.environ.get("DATABASE_URL") or "sqlite:///./backend/data/confit.db"



from backend.app.core.postgres_url import normalise_postgres_url  # noqa: F401  (re-export)


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
