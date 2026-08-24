import os
import ssl
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from backend.app.core.config import settings

# Load database URL exclusively from environment or fallback to local SQLite for dev
raw_url = settings.DATABASE_URL or os.environ.get("DATABASE_URL") or "sqlite:///./backend/data/confit.db"

connect_args = {}
if "postgres" in raw_url:
    if "pg8000" in raw_url or "sslmode=" in raw_url:
        if not raw_url.startswith("postgresql+pg8000://"):
            raw_url = raw_url.replace("postgresql://", "postgresql+pg8000://", 1).replace("postgres://", "postgresql+pg8000://", 1)
        if "sslmode=" in raw_url:
            raw_url = raw_url.split("?")[0]
        ctx = ssl.create_default_context()
        connect_args = {"ssl_context": ctx}
    elif raw_url.startswith("postgres://"):
        raw_url = raw_url.replace("postgres://", "postgresql://", 1)
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
