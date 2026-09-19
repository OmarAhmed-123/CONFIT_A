"""Diagnostic probe (2026-09-16): capture the AT-15 N=2 layer-2 (blazer outer)
render BEFORE the sleeve gate decides, to classify the AT-15 red as either
(a) gate over-refusal (sleeves visually present, thin margin) or
(b) genuine engine gap (sleeves partially/absent in the render).

Reproduces test_at15_dynamic_layering_n2 exactly:
  person = person_rt1.jpg
  layer 1 = AT Teal Tee (garment_rt1.jpg, short-sleeve, upper_inner)
  layer 2 = catalog first outerwear = product 1 (seed blazer, long-sleeve)
Production code path (TestClient -> TryOnService -> live worker); the only
instrumentation is a capture wrapper around the sleeve gate that saves the
layer's output/input/garment images and then runs the REAL gate (behavior
unchanged; REFUSE still fails the job).
"""
import base64
import io
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "backend" / "tests"))
sys.path.insert(0, str(REPO / "evaluation"))

# --- live worker env (same as the live_env fixture) -------------------------
urls = (REPO / "evaluation" / ".eval_urls").read_text().split()
env_text = (REPO / "evaluation" / ".eval_env").read_text()
token = re.search(r"^VTON_EVAL_ADMIN_TOKEN=(.+)$", env_text, re.M).group(1).strip()
os.environ["VTON_WORKER_URL"] = urls[1]
os.environ["VTON_WORKER_PROCESS_URL"] = urls[1]
os.environ["VTON_WORKER_HEALTH_URL"] = urls[0]
os.environ["VTON_WORKER_READINESS_URL"] = urls[0]
os.environ["VTON_WORKER_ADMIN_TOKEN"] = token
os.environ.setdefault("CONFIT_VTON_DISABLE_REMBG", "1")

# --- test DB (same as conftest) ---------------------------------------------
os.chdir(REPO)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import get_db, engine as app_engine
from backend.app.seed_data import seed_database
from backend.app.main import app

TEST_DB_URL = "sqlite:///./backend/data/confit_test.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
app.state.limiter.enabled = False
seed_database(target_engine=test_engine, force=True)
seed_database(target_engine=app_engine, force=True)

# --- capture wrapper around the sleeve gate ---------------------------------
CAPTURES = []
import backend.app.services.vton_sleeve_gate as gate_mod
import backend.app.services.tryon_service as svc

_real_gate = svc.evaluate_layer_sleeves

def _b64_save(data_url, path):
    raw = base64.b64decode(data_url.split(",", 1)[1])
    path.write_bytes(raw)

async def capturing_gate(*, slot_type, sleeve_length, output_data_url,
                         input_data_url, garment_ref, product_id=None, layer=None):
    try:
        _b64_save(output_data_url, Path(f"/tmp/at15_layer{layer}_output.png"))
        _b64_save(input_data_url, Path(f"/tmp/at15_layer{layer}_input.png"))
        if isinstance(garment_ref, str) and garment_ref.startswith("data:image"):
            _b64_save(garment_ref, Path(f"/tmp/at15_layer{layer}_garment.png"))
        CAPTURES.append({
            "layer": layer, "product_id": product_id, "slot_type": slot_type,
            "sleeve_length": sleeve_length,
            "output_sha256": __import__("hashlib").sha256(
                base64.b64decode(output_data_url.split(",", 1)[1])).hexdigest(),
        })
    except Exception as e:  # noqa: BLE001
        print("capture failed:", type(e).__name__, str(e)[:200])
    return await _real_gate(
        slot_type=slot_type, sleeve_length=sleeve_length,
        output_data_url=output_data_url, input_data_url=input_data_url,
        garment_ref=garment_ref, product_id=product_id, layer=layer,
    )

svc.evaluate_layer_sleeves = capturing_gate

# --- reproduce AT-15 ----------------------------------------------------------
from starlette.testclient import TestClient

db = TestingSessionLocal()
from backend.app.models.catalog import Product
outer = db.query(Product).filter(Product.id == 1).first()
print("outer product:", outer.id, outer.title, "sleeve_length:", outer.sleeve_length)

def data_url(p: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode()

def make_top():
    from backend.tests.test_architecture_dynamic import _make_product
    return _make_product(db, "tops", "AT Teal Tee (probe)",
                         data_url(REPO / "evaluation/archtest_inputs/garment_rt1.jpg"),
                         "#2E7F8F", sleeve_length="short")

g1 = make_top()
print("g1:", g1)

person = data_url(REPO / "evaluation/archtest_inputs/person_rt1.jpg")

client = TestClient(app)
t0 = time.time()
r = client.post("/api/v1/tryon/multi-render",
                json={"product_ids": [g1, outer.id], "user_image_base64": person})
print("POST", r.status_code, "in", round(time.time() - t0, 1), "s")
body = r.json()
print("status:", body.get("status"), "| error_code:", body.get("error_code"))
print("error:", str(body.get("error") or body.get("detail") or "")[:300])
print("verification:", json.dumps(body.get("verification"), default=str)[:200])
print("captures:", json.dumps(CAPTURES, indent=1, default=str))

for f in Path("/tmp").glob("at15_layer*"):
    im = Image.open(f)
    print(f.name, im.size)
