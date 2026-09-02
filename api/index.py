"""Vercel serverless entrypoint for the CONFIT API.

Imports the canonical backend package from the repository root. The vendored
copy previously kept under api/backend/ was removed (it drifted from the real
backend and every fix had to be applied twice); Vercel bundles the whole
project, so the root backend/ package is always available here.

Simplified path handling: only parent_dir is needed as Vercel sets /var/task as cwd.
"""

import sys
import os

# Vercel bundles project root at /var/task - parent_dir is the repo root
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from backend.app.main import app  # noqa: E402

__all__ = ["app"]
