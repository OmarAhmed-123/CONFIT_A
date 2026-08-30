from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.core.config import settings
from backend.app.core.logging import setup_logging, logger
from backend.app.core.database import engine, Base
from backend.app.core.dependencies import get_current_user
from backend.app.core.exceptions import AuthorizationError, ConfitException
from backend.app.models.user import UserRole
from backend.app.controllers.auth_controller import router as auth_router
from backend.app.controllers.profile_controller import router as profile_router
from backend.app.controllers.catalog_controller import router as catalog_router
from backend.app.controllers.stylist_controller import router as stylist_router
from backend.app.controllers.outfit_controller import router as outfit_router
from backend.app.controllers.tryon_controller import router as tryon_router
from backend.app.controllers.wardrobe_controller import router as wardrobe_router
from backend.app.controllers.commerce_controller import router as commerce_router
from backend.app.controllers.brand_controller import router as brand_router
from backend.app.controllers.admin_controller import router as admin_router
from backend.app.controllers.telemetry_controller import router as telemetry_router
from backend.app.controllers.moodboard_controller import router as moodboard_router
from backend.app.core.rate_limit import limiter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from fastapi.staticfiles import StaticFiles
import os

setup_logging(debug=settings.DEBUG)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing CONFIT API Engine", version=settings.VERSION, env=settings.ENVIRONMENT)
    # Group 1 §40: production schema is managed by Alembic
    #     PYTHONPATH=. alembic -c backend/alembic.ini upgrade head
    # We STILL call create_all() below for the dev/CI convenience path so
    # tests and fresh checkouts remain one-command runnable — but a
    # production deployment MUST NOT rely on it: startup skips it entirely
    # when ENVIRONMENT=production, forcing the operator to run migrations.
    try:
        if settings.ENVIRONMENT.lower() != "production":
            Base.metadata.create_all(bind=engine)
            # Seed guard level 1 (startup): demo catalogue + demo accounts are
            # a development convenience only. In production the operator runs
            # Alembic migrations and the app must NEVER auto-create known
            # credentials like admin@confit.io / Password123!.
            from sqlalchemy.orm import Session as _Session
            from backend.app.models.catalog import Category
            with _Session(engine) as _s:
                if _s.query(Category).count() == 0:
                    from backend.app.seed_data import seed_database
                    seed_database(target_engine=engine)
                    logger.info("Database was empty — seeded the default catalogue")
    except Exception as exc:
        logger.warn("Database initialization notice", error=str(exc))
    yield
    logger.info("Shutting down CONFIT API Engine")


app = FastAPI(
    title="CONFIT — Fashion Tech Core API",
    description="Enterprise-grade REST API powering the CONFIT AI Fashion Platform across G1–G6.",
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Rate limiting (429 on breach) — registered before routes so limits apply.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# CSRF protection for cookie-authenticated requests (double-submit pattern).
# Requests authenticated by a Bearer header are immune by design (headers
# can't be forged cross-site); requests authenticated by the httpOnly cookie
# must present X-CSRF-Token matching the readable confit_csrf cookie.
CSRF_EXEMPT_PATH_PREFIXES = ("/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/social-login", "/v1/auth/", "/auth/")


@app.middleware("http")
async def csrf_cookie_guard(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        has_session_cookie = "confit_token" in request.cookies
        has_bearer = (request.headers.get("authorization") or "").startswith("Bearer ")
        if has_session_cookie and not has_bearer:
            path = request.url.path
            if not any(path.startswith(p) for p in CSRF_EXEMPT_PATH_PREFIXES):
                csrf_cookie = request.cookies.get("confit_csrf")
                csrf_header = request.headers.get("x-csrf-token")
                if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
                    return JSONResponse(
                        status_code=403,
                        content={"error": {"code": "CSRF_TOKEN_MISMATCH", "message": "CSRF token missing or invalid.", "details": {}}},
                    )
    return await call_next(request)


# Exception handler for domain exceptions
@app.exception_handler(ConfitException)
async def confit_exception_handler(request: Request, exc: ConfitException):
    logger.warn(
        "Domain exception occurred",
        path=request.url.path,
        error_code=exc.code,
        message=exc.message,
        details=exc.details
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details
            }
        }
    )


# Exception handler for general exceptions
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled server exception", path=request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred. Our engineering team has been notified.",
                "details": {}
            }
        }
    )


# Register API routers with multi-prefix support for Vercel Serverless & Local Dev
for prefix in [settings.API_V1_STR, "/v1", ""]:
    app.include_router(telemetry_router, prefix=prefix)
    app.include_router(auth_router, prefix=prefix)
    app.include_router(profile_router, prefix=prefix)
    app.include_router(catalog_router, prefix=prefix)
    app.include_router(stylist_router, prefix=prefix)
    app.include_router(outfit_router, prefix=prefix)
    app.include_router(tryon_router, prefix=prefix)
    app.include_router(wardrobe_router, prefix=prefix)
    app.include_router(commerce_router, prefix=prefix)
    app.include_router(brand_router, prefix=prefix)
    app.include_router(admin_router, prefix=prefix)
    app.include_router(moodboard_router, prefix=prefix)

# Mount static files for user uploads only. The legacy /tryon_results static
# mount was removed together with the purged pre-rendered assets: try-on
# outputs must come from a real render (GPU worker + object storage), never
# from bundled static files.
uploads_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "uploads"))
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

# Root route
@app.get("/")
def root():
    return {
        "platform": "CONFIT",
        "tagline": "Where Style Meets Your Character in Every Moment",
        "api_documentation": "/docs",
        "status": "operational",
        "version": settings.VERSION
    }


def _require_diagnostic_access(user=Depends(get_current_user)):
    """Group 1 §4: the diagnostic endpoint is never public and never exists
    in production. Outside production it is admin-only. It returns only
    aggregate, non-sensitive liveness data — never user identities, database
    URLs/credentials, filesystem paths, or raw tracebacks."""
    if settings.ENVIRONMENT.lower() == "production":
        raise HTTPException(status_code=404, detail="Not found")
    if user.role != UserRole.ADMIN:
        raise AuthorizationError("Diagnostic endpoint is restricted to administrators.")
    return user


@app.get("/api/v1/diagnostic", include_in_schema=False)
def diagnostic(admin_user=Depends(_require_diagnostic_access)):
    from backend.app.core.database import SessionLocal
    from backend.app.models.user import User
    from sqlalchemy import func
    db = SessionLocal()
    try:
        users_count = db.query(func.count(User.id)).scalar() or 0
        db_ok = True
    except Exception:
        users_count = None
        db_ok = False
    finally:
        db.close()
    return {
        "status": "ok" if db_ok else "db_error",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "database_reachable": db_ok,
        "users_count": users_count,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
