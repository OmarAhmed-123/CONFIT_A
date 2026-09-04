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

engine = create_engine(
    raw_url,
    connect_args=connect_args,
    pool_pre_ping=True,
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
