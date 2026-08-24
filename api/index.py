import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
for p in [current_dir, parent_dir, "/var/task"]:
    if p not in sys.path and os.path.exists(p):
        sys.path.insert(0, p)

from backend.app.main import app
