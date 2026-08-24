import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from backend.app.core.config import settings

is_serverless = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
prod_neon_db = "postgresql://neondb_owner:npg_LV59RjkGCHeZ@ep-frosty-term-b2ivqwuz-pooler.c-6.eu-central-1.aws.neon.tech/neondb?sslmode=require"

db_url = settings.DATABASE_URL or (prod_neon_db if is_serverless else "sqlite:///./backend/data/confit.db")
if is_serverless and ("sqlite" in db_url or not db_url):
    db_url = prod_neon_db

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
