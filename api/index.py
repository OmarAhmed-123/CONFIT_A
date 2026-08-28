"""Vercel serverless entrypoint for the CONFIT API.

Imports the canonical backend package from the repository root. The vendored
copy previously kept under api/backend/ was removed (it drifted from the real
backend and every fix had to be applied twice); Vercel bundles the whole
project, so the root backend/ package is always available here.
"""

import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)

for p in [parent_dir, current_dir, "/var/task"]:
    if p not in sys.path and os.path.exists(p):
        sys.path.insert(0, p)

from backend.app.main import app  # noqa: E402

__all__ = ["app"]
