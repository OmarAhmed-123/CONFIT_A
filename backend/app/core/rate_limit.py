"""Shared rate limiter (slowapi).

Cost control, not just hardening: /try-on/* endpoints trigger real GPU spend
per call once the worker is deployed, and /auth/* endpoints are the brute-force
surface. Keyed per client IP. Tests disable the limiter globally and re-enable
it only inside the dedicated 429 proof test.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
