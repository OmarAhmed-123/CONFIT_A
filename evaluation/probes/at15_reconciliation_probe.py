"""AT-15 reconciliation probe (2026-09-16, Phase 2, P4).

Questions (evidence only; no threshold change):
  R1. Reproducibility: same composition (person rt1 + AT teal tee + catalog
      seed blazer, layer 2) re-rendered now -> does it reproduce the
      2026-09-16 measurement (best-arm 0.3282, output sha d60ef293...)?
  R2. Mutation class (one variable at a time, seed blazer held constant):
      m1 lighter trousers  (fresh person C, beige joggers)
      m2 darker background (fresh person D, dark backdrop)
      m3 different pose    (fresh person E, arms raised)
      m4 different person  (fresh person A, light bg, dark jeans)
      m5 different inner   (burgundy long-sleeve top instead of short tee)
  -> separates "intrinsic to the metric geometry (dark blazer over the band)"
     from "composition-specific (this person / these trousers / this bg)".

Production path (TestClient -> TryOnService -> live worker); capture wrapper
preserves production semantics (REFUSE still fails the job).
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

import backend.app.services.vton_sleeve_gate as gate_mod
import backend.app.services.tryon_service as svc

health = httpx.get(urls[0], headers={"X-VTON-Admin": token}, timeout=60).json()
WORKER = {"model": health.get("model"), "git_sha": health.get("git_sha"),
          "device": health.get("device"), "service": health.get("service")}
print("WORKER:", json.dumps(WORKER), flush=True)

OUT = REPO / "evaluation" / "results" / "at15_reconciliation"
OUT.mkdir(parents=True, exist_ok=True)

CAPTURES = []
CURRENT = None
_real_gate = svc.evaluate_layer_sleeves

def score_layer(cid, layer, out_p, in_p, gar_p):
    out_img = Image.open(out_p).convert("RGB")
    in_img = Image.open(in_p).convert("RGB")
    ref = gate_mod.garment_dominant_lab(Image.open(gar_p).convert("RGB"))
    if ref == (0.0, 0.0, 0.0):
        return {"degenerate_color": True}
    scores = {}
    orig = gate_mod.FOREARM_CHANGE_THRESHOLD
    try:
        for t in (15.0, 20.0, 25.0, 30.0):
            gate_mod.FOREARM_CHANGE_THRESHOLD = t
            scores[str(t)] = gate_mod.forearm_garment_coverage(out_img, in_img, ref)
    finally:
        gate_mod.FOREARM_CHANGE_THRESHOLD = orig
    return {"ref_lab": [round(v, 1) for v in ref], "sweep": scores,
            "best_20": max(scores["20.0"].values())}

async def capturing_gate(*, slot_type, sleeve_length, output_data_url,
                         input_data_url, garment_ref, product_id=None, layer=None):
    cid = CURRENT
    out_p = OUT / f"{cid}_L{layer}.png"
    in_p = OUT / f"{cid}_L{layer}_input.png"
    gar_p = OUT / f"{cid}_L{layer}_garment.png"
    cap = {"layer": layer, "product_id": product_id, "slot_type": slot_type,
           "sleeve_length": sleeve_length}
    try:
        raw_out = base64.b64decode(output_data_url.split(",", 1)[1])
        out_p.write_bytes(raw_out)
        in_p.write_bytes(base64.b64decode(input_data_url.split(",", 1)[1]))
        if isinstance(garment_ref, str) and garment_ref.startswith("data:image"):
            gar_p.write_bytes(base64.b64decode(garment_ref.split(",", 1)[1]))
        cap["output_sha256"] = hashlib.sha256(raw_out).hexdigest()
    except Exception as e:  # noqa: BLE001
        cap["capture_error"] = f"{type(e).__name__}: {str(e)[:150]}"
    raised = None
    try:
        decision = await _real_gate(slot_type=slot_type, sleeve_length=sleeve_length,
                                    output_data_url=output_data_url,
                                    input_data_url=input_data_url,
                                    garment_ref=garment_ref,
                                    product_id=product_id, layer=layer)
        cap["gate_status"] = decision.get("status")
        cap["gate_reason"] = str(decision.get("reason"))[:300]
        cap["gate_coverage"] = decision.get("coverage")
    except Exception as e:  # noqa: BLE001
        raised = e
        cap["gate_status"] = "REFUSE"
        cap["gate_reason"] = str(e)[:300]
    try:
        cap["scores"] = score_layer(cid, layer, out_p, in_p, gar_p)
    except Exception as e:  # noqa: BLE001
        cap["score_error"] = f"{type(e).__name__}: {str(e)[:120]}"
    CAPTURES.append(cap)
    if raised is not None:
        raise raised
    return decision

svc.evaluate_layer_sleeves = capturing_gate

def data_url(p: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode()

from backend.tests.test_architecture_dynamic import _make_product
from starlette.testclient import TestClient
client = TestClient(app)

FRESH = REPO / "evaluation" / "dyninputs_fresh"
ARCH = REPO / "evaluation" / "archtest_inputs"

CASES = [
    ("m0_repro", ARCH / "person_rt1.jpg", "teal_tee"),
    ("m1_light_trousers", FRESH / "person_C.jpg", "teal_tee"),
    ("m2_dark_bg", FRESH / "person_D.jpg", "teal_tee"),
    ("m3_arms_raised", FRESH / "person_E.jpg", "teal_tee"),
    ("m4_diff_person", FRESH / "person_A.jpg", "teal_tee"),
    ("m5_dark_inner", ARCH / "person_rt1.jpg", "burgundy_ls"),
]

from backend.app.models.catalog import Product
db = TestingSessionLocal()
outer = db.query(Product).filter(Product.id == 1).first()
print("outer:", outer.id, outer.title, "sleeve:", outer.sleeve_length)

def make_top(slug, title, img, hex, sleeve):
    return _make_product(db, slug, title, data_url(img), hex, sleeve_length=sleeve)

RESULTS = {"worker": WORKER, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "reference": {"original_measurement": "2026-09-16: L2 best-arm 0.3282 @thr20, output sha256 d60ef293...", "composition": "person_rt1 + AT teal tee (short) + product 1 seed blazer (long)"},
           "cases": {}}

for cid, person_p, top in CASES:
    db = TestingSessionLocal()
    try:
        if top == "teal_tee":
            g1 = make_top("tops", f"AT15R {cid} teal tee", ARCH / "garment_rt1.jpg", "#2E7F8F", "short")
        else:
            g1 = make_top("tops", f"AT15R {cid} burgundy ls", ARCH / "garment_rt4.jpg", "#6E2233", "long")
    finally:
        db.close()
    CAPTURES.clear()
    CURRENT = cid
    t0 = time.time()
    r = client.post("/api/v1/tryon/multi-render",
                    json={"product_ids": [g1, outer.id],
                          "user_image_base64": base64.b64encode(person_p.read_bytes()).decode(),
                          "avatar_model_id": None, "gender_mode": "infer_from_image"})
    elapsed = round(time.time() - t0, 1)
    try:
        j = r.json()
    except Exception:  # noqa: BLE001
        j = None
    detail = (j or {}).get("detail")
    err = detail.get("error", {}) if isinstance(detail, dict) else {}
    entry = {"http": r.status_code, "elapsed_s": elapsed,
             "error_code": err.get("code"),
             "error_message": str(err.get("message", ""))[:250],
             "layers": list(CAPTURES)}
    out_url = (j or {}).get("rendered_result_url")
    if isinstance(out_url, str) and out_url.startswith("data:"):
        final = base64.b64decode(out_url.split(",", 1)[1])
        (OUT / f"{cid}_final.png").write_bytes(final)
        entry["final_sha256"] = hashlib.sha256(final).hexdigest()
    RESULTS["cases"][cid] = entry
    for l in entry["layers"]:
        s = (l.get("scores") or {})
        print(f"{cid:18} L{l['layer']} {str(l.get('gate_status')):6} "
              f"best20={s.get('best_20')} sha={str(l.get('output_sha256',''))[:10]}", flush=True)

(OUT / "results.json").write_text(json.dumps(RESULTS, indent=1, default=str))
print("WROTE", OUT / "results.json", flush=True)
