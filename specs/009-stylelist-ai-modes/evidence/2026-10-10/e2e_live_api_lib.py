import os
import base64, io, json, os, sqlite3, httpx
from PIL import Image
BASE = "http://127.0.0.1:8000/api/v1"
DB = os.environ.get("E2E_DB", "/home/user/.cache/confit-e2e/e2e.db")  # local test DB only
PASSWORD = os.environ["E2E_PASSWORD"]  # local seeded test account only; never commit a value

def _csrf_value(c):
    vals = [ck.value for ck in c.cookies.jar if ck.name == "confit_csrf"]
    return vals[-1] if vals else ""

def login(email):
    c = httpx.Client(base_url=BASE, timeout=60)
    r = c.post("/auth/login", json={"email": email, "password": PASSWORD})
    r.raise_for_status()
    return c

def csrf(c):
    return {"X-CSRF-Token": _csrf_value(c)}

def png_data_url(colour=(40, 60, 120), size=(64, 64)):
    buf = io.BytesIO(); Image.new("RGB", size, colour).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

def db():
    return sqlite3.connect(DB)
