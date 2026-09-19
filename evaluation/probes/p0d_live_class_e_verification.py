"""P0-D Phase-5 LIVE verification of the sleeve-FP fix (v2.3 gate).

Re-runs the EXACT class-E composition that the v2.2 gate FALSE-PASSED
(person J + garment_arabic_tee_2, declared long-sleeve; the 2026-09-16
artifact p4_j_arabic2 rendered sleeveless, coverage 0.7062 -> PASS) through
the CURRENT production chain (v2.3 anatomical integrity channels in place),
via the live worker. Records HTTP status, canonical error code, and the
per-layer gate decision (coverage + anatomy) so the report can state, with
live evidence, whether the false pass is eliminated end-to-end.

Labels: AGENT VISUAL INSPECTION — NOT HUMAN GROUND TRUTH.
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

import httpx
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import get_db, engine as app_engine
from backend.app.seed_data import seed_database
from backend.app.main import app

TEST_DB_URL = "sqlite:///./backend/data/confit_p0d_test.db"
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
import backend.app.services.vton_sleeve_gate as gate_mod

def health():
    return httpx.get(urls[0], headers={"X-VTON-Admin": token}, timeout=60).json()

WORKER = {k: health().get(k) for k in ("model", "device", "git_sha", "service", "ready")}
print("WORKER:", json.dumps(WORKER), flush=True)

OUT = REPO / "evaluation" / "results" / "p0d_live_class_e"
OUT.mkdir(parents=True, exist_ok=True)

CAPTURES = []
CURRENT = None
_real_gate = svc.evaluate_layer_sleeves

async def capturing_gate(*, slot_type, sleeve_length, output_data_url,
                         input_data_url, garment_ref, product_id=None, layer=None):
    cid = CURRENT
    cap = None
    if sleeve_length == "long" and slot_type in ("upper_inner", "upper_outer", "dress"):
        cap = {"layer": layer, "product_id": product_id, "slot_type": slot_type}
        try:
            out_p = OUT / f"{cid}_L{layer}.png"
            in_p = OUT / f"{cid}_L{layer}_input.png"
            gar_p = OUT / f"{cid}_L{layer}_garment.png"
            out_p.write_bytes(base64.b64decode(output_data_url.split(",", 1)[1]))
            in_p.write_bytes(base64.b64decode(input_data_url.split(",", 1)[1]))
            if isinstance(garment_ref, str) and garment_ref.startswith("data:image"):
                gar_p.write_bytes(base64.b64decode(garment_ref.split(",", 1)[1]))
            # measure with the CURRENT (v2.3) sync core for provenance
            from backend.app.services.vton_sleeve_gate import evaluate_sleeves_sync
            d = evaluate_sleeves_sync(
                slot_type=slot_type, sleeve_length=sleeve_length,
                output_img=Image.open(out_p).convert("RGB"),
                input_img=Image.open(in_p).convert("RGB"),
                garment_img=Image.open(gar_p).convert("RGB"))
            cap["measured"] = {
                "status": d["status"],
                "coverage": d.get("coverage"),
                "anatomy": d.get("anatomy"),
                "reason": str(d.get("reason"))[:220],
            }
        except Exception as e:  # noqa: BLE001
            cap["measure_error"] = f"{type(e).__name__}: {str(e)[:120]}"
        CAPTURES.append(cap)
    raised = None
    try:
        decision = await _real_gate(slot_type=slot_type, sleeve_length=sleeve_length,
                                    output_data_url=output_data_url,
                                    input_data_url=input_data_url,
                                    garment_ref=garment_ref, product_id=product_id,
                                    layer=layer)
        if cap is not None:
            cap["gate_status"] = decision.get("status")
    except Exception as e:  # noqa: BLE001
        raised = e
        if cap is not None:
            cap["gate_status"] = "REFUSE(raise)"
            cap["gate_reason"] = str(e)[:240]
    if raised is not None:
        raise raised
    return decision

svc.evaluate_layer_sleeves = capturing_gate

from backend.tests.test_architecture_dynamic import _make_product
from starlette.testclient import TestClient
client = TestClient(app)

FRESH = REPO / "evaluation" / "dyninputs_fresh"

def data_url(p: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode()

db = TestingSessionLocal()
gar_img = FRESH / "garment_arabic_tee_2.jpg"
prod_id = _make_product(db, "arabic_tee_2_p0d", "P0D class-E live verification", data_url(gar_img),
                        "#888888", sleeve_length="long")
db.close()

CASES = [
    ("p0d_j_arabic2", "J"),   # the class-E composition
]

RESULTS = {"worker": WORKER,
           "note": "class-E composition re-run through the v2.3 production chain; "
                   "AGENT VISUAL INSPECTION — NOT HUMAN GROUND TRUTH",
           "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "cases": {}}

for cid, person_key in CASES:
    person = base64.b64encode((FRESH / f"person_{person_key}.jpg").read_bytes()).decode()
    CAPTURES.clear()
    CURRENT = cid
    t0 = time.time()
    r = None
    j = {}
    post_error = None
    try:
        r = client.post("/api/v1/tryon/multi-render",
                        json={"product_ids": [prod_id], "user_image_base64": person,
                              "avatar_model_id": None, "gender_mode": "infer_from_image"})
        j = r.json()
    except Exception as e:  # noqa: BLE001
        post_error = f"{type(e).__name__}: {str(e)[:200]}"
    detail = j.get("detail")
    err = detail.get("error", {}) if isinstance(detail, dict) else {}
    entry = {"person": person_key, "garment": "garment_arabic_tee_2 (declared long)",
             "http": r.status_code if r is not None else None,
             "post_error": post_error,
             "error_code": err.get("code"),
             "elapsed_s": round(time.time() - t0, 1),
             "sleeve": [dict(c) for c in CAPTURES]}
    out_url = j.get("rendered_result_url") or j.get("result_image_data_url")
    if isinstance(out_url, str) and out_url.startswith("data:"):
        raw = base64.b64decode(out_url.split(",", 1)[1])
        entry["final_sha8"] = hashlib.sha256(raw).hexdigest()[:8]
        (OUT / f"{cid}_final.png").write_bytes(raw)
    RESULTS["cases"][cid] = entry
    s = CAPTURES[0] if CAPTURES else {}
    print(f"{cid} http={entry['http']} code={str(entry['error_code'])[:30]} "
          f"measured={s.get('measured', {}).get('status')} "
          f"cov={s.get('measured', {}).get('coverage')} "
          f"anat={s.get('measured', {}).get('anatomy')} {entry['elapsed_s']}s", flush=True)

RESULTS["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
(OUT / "results.json").write_text(json.dumps(RESULTS, indent=1, default=str))
print("WROTE", OUT / "results.json", flush=True)
