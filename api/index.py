import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
api_backend_dir = os.path.join(current_dir, "backend")

for p in [current_dir, parent_dir, api_backend_dir, "/var/task", "/var/task/api"]:
    if p not in sys.path and os.path.exists(p):
        sys.path.insert(0, p)

try:
    from backend.app.main import app
except Exception:
    from api.backend.app.main import app
