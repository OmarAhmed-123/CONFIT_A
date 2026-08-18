import sys
import os

# Add root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.main import app

try:
    from mangum import Mangum
    handler = Mangum(app)
except Exception:
    handler = app
