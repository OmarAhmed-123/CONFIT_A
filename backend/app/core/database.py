import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from backend.app.core.config import settings

db_url = settings.DATABASE_URL or "sqlite:///./backend/data/confit.db"
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# Ensure local data directory only for SQLite in local development
if "sqlite" in db_url:
    try:
        sqlite_path = db_url.replace("sqlite:///", "")
        dir_name = os.path.dirname(sqlite_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
    except Exception:
        pass

connect_args = {"check_same_thread": False} if "sqlite" in db_url else {}

engine = create_engine(
    db_url,
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
