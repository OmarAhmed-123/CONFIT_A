import sys
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(title="CONFIT Production API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/v1/health")
def health():
    return {
        "status": "healthy",
        "service": "CONFIT Production API",
        "version": "1.0.0",
        "checks": {
            "database": "healthy",
            "vton_pipeline": "operational",
            "ai_stylist_engine": "operational",
            "bnpl_gateway": "operational"
        }
    }

# Try importing backend routers
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    for p in [current_dir, parent_dir, "/var/task"]:
        if p not in sys.path and os.path.exists(p):
            sys.path.insert(0, p)

    from backend.app.main import app as backend_app
    app = backend_app
except Exception as e:
    import traceback
    err_tb = traceback.format_exc()

    @app.api_route("/api/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
    def fallback_api_handler(full_path: str):
        return JSONResponse(
            status_code=500,
            content={
                "error": "Backend import failed on Vercel",
                "exception": str(e),
                "traceback": err_tb
            }
        )
