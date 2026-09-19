"""N=2 determinism + one-variable re-runs (Phase 3, 2026-09-16).

P2/P3 controlled re-runs (production path, fresh catalog rows = same image
bytes under new product rows, fresh job ids each call):

  D1  n2_A_T1_B1  (A teal-tee + olive chino)  — FAIL in matrix; x3 repeats
  D2  n2_I_T1_B2  (I teal-tee + navy trousers) — FAIL in matrix; x3 repeats
  D3  n2_A_T1_B2  (A teal-tee + navy trousers) — PASS in matrix; x3 repeats
  D4  delayed re-run of D1 (60 s after D1-3) to probe worker-state drift
  D5  n2_C_T1_B3  (C teal-tee + beige chino)   — FAIL in matrix; x3 repeats
      (the C+beige case that PASSED with the rust top T3: controlled
       one-variable check that the top/L1 output is the changing variable)

Per run records: L1 output sha256 + bytes, L2 output sha256, L2 verify
metrics, decision. Answers: is L1 byte-deterministic? is the L2 decision
deterministic given (L1 bytes, bottom)? does anything flip?
"""
import base64
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "backend" / "tests"))
sys.path.insert(0, str(REPO / "evaluation"))

urls = (REPO / "evaluation" / ".eval_urls").read_text().split()
env_text = (REPO / "evaluation" / ".eval_env").read_text()
token = re.search(r"^VTON_EVAL_ADMIN_TOKEN=(.+)$", env_text, re.M).group(1).strip()
os.environ["VTON_WORKER_URL"] = urls[1]
os.environ["VTON_WORKER_PROCESS_URL"] = urls[1]
os.environ["VTON_WORKER_HEALTH_URL"] = urls[0]
os.environ["VTON_WORKER_READINESS_URL"] = urls[0]
os.environ["VTON_WORKER_ADMIN_TOKEN"] = token
os.environ.setdefault("CONFIT_VTON_DISABLE_REMBG", "1")
os.chdir(REPO)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from PIL import Image

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

import backend.app.services.tryon_service as svc

CAPS = []
_real_call = svc.TryOnService._call_gpu_worker

async def capturing_call(self, job_id, person_image, garments,
                         gender_mode="infer_from_image", output_aspect="9:16"):
    cap = {"job_id": job_id, "t0": time.time()}
    try:
        gpu = await _real_call(self, job_id=job_id, person_image=person_image,
                               garments=garments, gender_mode=gender_mode,
                               output_aspect=output_aspect)
        cap["ok"] = True
        rend = gpu.get("rendered_image_data_url", "")
        raw = base64.b64decode(rend.split(",", 1)[1]) if rend.startswith("data:") else b""
        cap["rendered_sha256"] = hashlib.sha256(raw).hexdigest()
        cap["rendered_bytes"] = len(raw)
        cap["verify"] = gpu.get("verify")
        CAPS.append(cap)
        return gpu
    except Exception as e:  # noqa: BLE001
        cap["ok"] = False
        cap["error"] = str(e)[:300]
        CAPS.append(cap)
        raise

svc.TryOnService._call_gpu_worker = capturing_call

FRESH = REPO / "evaluation" / "dyninputs_fresh"
ARCH = REPO / "evaluation" / "archtest_inputs"
OUT = REPO / "evaluation" / "results" / "n2_determinism"
OUT.mkdir(parents=True, exist_ok=True)

from backend.app.models.catalog import Product
from backend.tests.test_architecture_dynamic import _make_product
from starlette.testclient import TestClient
client = TestClient(app)

_db = TestingSessionLocal()
NAVY = _db.query(Product).filter(
    Product.title == "Pleated Tapered Virgin Wool Trousers").first()
_db.close()

def data_url(p: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode()

def render(person_key, top_img, top_sleeve, bottom_kind, bottom_img=None):
    db = TestingSessionLocal()
    try:
        if bottom_kind == "navy":
            bottom_id = NAVY.id
        else:
            bottom_id = _make_product(db, "bottoms", f"det {bottom_kind}",
                                      data_url(bottom_img), "#888888", sleeve_length="none")
        top_id = _make_product(db, "tops", "det top", data_url(top_img),
                               "#2E7F8F", sleeve_length=top_sleeve)
    finally:
        db.close()
    person = base64.b64encode((FRESH / f"person_{person_key}.jpg").read_bytes()).decode()
    CAPS.clear()
    r = client.post("/api/v1/tryon/multi-render",
                    json={"product_ids": [top_id, bottom_id],
                          "user_image_base64": person,
                          "avatar_model_id": None,
                          "gender_mode": "infer_from_image"})
    try:
        j = r.json()
    except Exception:  # noqa: BLE001
        j = {}
    err = (j.get("detail") or {}).get("error", {}) if isinstance(j.get("detail"), dict) else {}
    return {"http": r.status_code, "error_code": err.get("code"), "layers": list(CAPS)}

CASES = [
    # (id, person, top_img, top_sleeve, bottom_kind, bottom_img)
    ("D1", "A", ARCH / "garment_rt1.jpg", "short", "olive", ARCH / "garment_rt2.jpg"),
    ("D2", "I", ARCH / "garment_rt1.jpg", "short", "navy", None),
    ("D3", "A", ARCH / "garment_rt1.jpg", "short", "navy", None),
    ("D5", "C", ARCH / "garment_rt1.jpg", "short", "beige", FRESH / "garment_beige_chino.jpg"),
]

RESULTS = {"started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "runs": []}

def do_run(cid, *args):
    e = render(*args)
    l1 = [c for c in e["layers"] if c["job_id"].endswith("_l1")]
    l2 = [c for c in e["layers"] if c["job_id"].endswith("_l2")]
    rec = {
        "case": cid,
        "decision": "PASS" if e["http"] == 200 else (e.get("error_code") or "?"),
        "l1_sha": l1[0].get("rendered_sha256") if l1 else None,
        "l1_bytes": l1[0].get("rendered_bytes") if l1 else None,
        "l2_sha": l2[0].get("rendered_sha256") if l2 else None,
        "l2_verify": l2[0].get("verify") if l2 else None,
        "l2_error": l2[0].get("error") if l2 else None,
        "job_ids": [c["job_id"] for c in e["layers"]],
        "t": time.strftime("%H:%M:%S"),
    }
    RESULTS["runs"].append(rec)
    print(f"{cid} http={e['http']} dec={rec['decision']} l1={str(rec['l1_sha'])[:12]} "
          f"l2v={json.dumps(rec['l2_verify']) if rec['l2_verify'] else '-'} {rec['t']}", flush=True)
    return rec

for cid, p, t_img, t_s, b_kind, b_img in CASES:
    for rep in (1, 2, 3):
        do_run(f"{cid}-{rep}", p, t_img, t_s, b_kind, b_img)

# D4: delayed re-run of D1 after 60 s
print("D4: waiting 60 s before delayed re-run...", flush=True)
time.sleep(60)
do_run("D4-delayed", "A", ARCH / "garment_rt1.jpg", "short", "olive", ARCH / "garment_rt2.jpg")

(OUT / "results.json").write_text(json.dumps(RESULTS, indent=1))
print("WROTE", OUT / "results.json", flush=True)
