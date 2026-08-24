import sys
import os
import traceback

# Ensure current dir and parent repository root are in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
for p in [current_dir, parent_dir, "/var/task", "/var/task/backend"]:
    if p not in sys.path and os.path.exists(p):
        sys.path.insert(0, p)

try:
    from backend.app.main import app
except Exception as e:
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    
    app = FastAPI(title="CONFIT Error Diagnostic")
    err_tb = traceback.format_exc()
    
    @app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
    def catch_all_error(path_name: str):
        return JSONResponse(
            status_code=500,
            content={
                "error": "Vercel serverless startup failed",
                "exception_type": type(e).__name__,
                "exception_message": str(e),
                "traceback": err_tb,
                "sys_path": sys.path,
                "current_dir": current_dir,
                "parent_dir_files": os.listdir(parent_dir) if os.path.exists(parent_dir) else [],
                "task_files": os.listdir("/var/task") if os.path.exists("/var/task") else []
            }
        )
