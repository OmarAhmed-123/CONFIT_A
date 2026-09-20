"""P0-C Phase-5: fresh sleeve-calibration artifacts (>=10 new beyond Parts 3-4).

Live cases (production path, catalog rows created per case, raw L1/input/
garment + final captured for the hermetic signal harness):

  p0c_k_white  K (white kurta input)  + white LS   — white-on-white
  p0c_f_white  F (white tunic, hijab) + white LS   — white-on-white + hijab
  p0c_m_black  M (navy shirt input)   + black LS   — dark-on-dark (#2)
  p0c_e_rust   E (arms raised)        + rust LS    — difficult pose
  p0c_a_pattern A                    + patterned LS — patterned garment
  p0c_g_short  G + short-sleeve tee DECLARED LONG  — genuine negative
  p0c_d_gray   D (bare-arm tank input)+ gray LS    — pre-existing bare-arm control
  p0c_l_black  L (plus-size, deep)    + black LS   — body-type + dark

Labels recorded are AGENT VISUAL INSPECTION — NOT HUMAN GROUND TRUTH.
Sleeve gate runs with production thresholds (20.0 / 0.35 / 0.15) — no
threshold moves; this batch collects artifacts + gate behavior for the
new anatomical-signal calibration.
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

TEST_DB_URL = "sqlite:///./backend/data/confit_p0c_test.db"
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

OUT = REPO / "evaluation" / "results" / "p0c_sleeve_calibration"
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
            ref = gate_mod.garment_dominant_lab(Image.open(gar_p).convert("RGB"))
            scores = {}
            for t in (15.0, 20.0, 25.0, 30.0):
                gate_mod.FOREARM_CHANGE_THRESHOLD = t
                scores[str(t)] = gate_mod.forearm_garment_coverage(
                    Image.open(out_p).convert("RGB"),
                    Image.open(in_p).convert("RGB"), ref)
            cap["sweep"] = scores
            cap["best_20"] = max(scores["20.0"].values())
            cap["ref_lab"] = [round(x, 1) for x in ref]
        except Exception as e:  # noqa: BLE001
            cap["score_error"] = f"{type(e).__name__}: {str(e)[:120]}"
        finally:
            gate_mod.FOREARM_CHANGE_THRESHOLD = 20.0
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
            cap["coverage"] = decision.get("coverage")
    except Exception as e:  # noqa: BLE001
        raised = e
        if cap is not None:
            cap["gate_status"] = "REFUSE(raise)"
            cap["gate_reason"] = str(e)[:200]
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

GAR = {
    "white_ls":   (FRESH / "garment_white_longsleeve.jpg", "tops", "long"),
    "black_ls":   (FRESH / "garment_black_longsleeve.jpg", "tops", "long"),
    "rust_ls":    (FRESH / "garment_rust_longsleeve.jpg", "tops", "long"),
    "gray_ls":    (FRESH / "garment_gray_longsleeve.jpg", "tops", "long"),
    "pattern_ls": (FRESH / "garment_patterned_ls.jpg", "tops", "long"),
    "short_tee":  (FRESH / "garment_short_sleeve_tee.jpg", "tops", "long"),  # DECLARED long (negative)
}

CASES = [
    ("p0c_k_white",   "K", "white_ls"),
    ("p0c_f_white",   "F", "white_ls"),
    ("p0c_m_black",   "M", "black_ls"),
    ("p0c_e_rust",    "E", "rust_ls"),
    ("p0c_a_pattern", "A", "pattern_ls"),
    ("p0c_g_short",   "G", "short_tee"),
    ("p0c_d_gray",    "D", "gray_ls"),
    ("p0c_l_black",   "L", "black_ls"),
]

db = TestingSessionLocal()
PROD = {}
for key, (img, slug, sleeve) in GAR.items():
    PROD[key] = _make_product(db, slug, f"P0C {key}", data_url(img), "#888888", sleeve_length=sleeve)
db.close()

RESULTS = {"worker": WORKER,
           "note": "AGENT VISUAL INSPECTION — NOT HUMAN GROUND TRUTH; "
                   "short_tee case is a genuine negative (short-sleeve garment declared long)",
           "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "cases": {}}

for cid, person_key, gkey in CASES:
    person = base64.b64encode((FRESH / f"person_{person_key}.jpg").read_bytes()).decode()
    CAPTURES.clear()
    CURRENT = cid
    t0 = time.time()
    try:
        r = client.post("/api/v1/tryon/multi-render",
                        json={"product_ids": [PROD[gkey]], "user_image_base64": person,
                              "avatar_model_id": None, "gender_mode": "infer_from_image"})
        j = r.json()
    except Exception:  # noqa: BLE001
        j = {}
    detail = j.get("detail")
    err = detail.get("error", {}) if isinstance(detail, dict) else {}
    entry = {"person": person_key, "garment": gkey,
             "http": r.status_code if hasattr(r, "status_code") else None,
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
    print(f"{cid:14} http={entry['http']} gate={s.get('gate_status')} best20={s.get('best_20')} "
          f"err={str(entry['error_code'])[:26]} {entry['elapsed_s']}s", flush=True)

RESULTS["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
(OUT / "results.json").write_text(json.dumps(RESULTS, indent=1, default=str))
print("WROTE", OUT / "results.json", flush=True)
