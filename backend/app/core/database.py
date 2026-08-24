import os
import ssl
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from backend.app.core.config import settings

is_serverless = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
prod_neon_db = "postgresql+pg8000://neondb_owner:npg_LV59RjkGCHeZ@ep-frosty-term-b2ivqwuz-pooler.c-6.eu-central-1.aws.neon.tech/neondb"

raw_url = settings.DATABASE_URL or (prod_neon_db if is_serverless else "sqlite:///./backend/data/confit.db")

connect_args = {}
if "pg8000" in raw_url or (is_serverless and "postgres" in raw_url):
    if not raw_url.startswith("postgresql+pg8000://"):
        raw_url = raw_url.replace("postgresql://", "postgresql+pg8000://", 1).replace("postgres://", "postgresql+pg8000://", 1)
    if "sslmode=" in raw_url:
        raw_url = raw_url.split("?")[0]
    ctx = ssl.create_default_context()
    connect_args = {"ssl_context": ctx}
elif "sqlite" in raw_url:
    connect_args = {"check_same_thread": False}
    try:
        sqlite_path = raw_url.replace("sqlite:///", "")
        dir_name = os.path.dirname(sqlite_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
    except Exception:
        pass
elif raw_url.startswith("postgres://"):
    raw_url = raw_url.replace("postgres://", "postgresql://", 1)

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
