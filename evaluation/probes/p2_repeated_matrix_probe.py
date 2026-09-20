"""P2 Phase-4: N=2 completeness matrix, repeated attempts, per class.

Combos (3 attempts each, production path, catalog IDs per attempt pair):
  n2tpb_pass  : A + teal tee (T1, short) + navy seed trousers   (pass class)
  n2tpb_fail  : B + burgundy LS (T2) + olive chino (B1)         (fail class)
  n2io_gray   : I + gray LS + dark blazer                       (inner+outer)
  s_top_b     : B + burgundy LS (single top)
  s_top_a     : A + teal tee (single top)
  s_bot_a     : A + navy seed trousers (single bottom)
  s_ow_i      : I + dark blazer (single outerwear)
  s_dress_g   : G + modest tunic (single dress)

Per attempt records: L1/L2 job id + sha + verify (PASS/pixel_change/
color_shift), sleeve-gate status per layer, final error code, elapsed.
Raw L1/L2/final worker bytes saved as artifacts (P2-A: raw L2 captured on
EVERY result, pass or fail, for engine-vs-gate classification).

Reports first-attempt vs repeated-attempt outcome PER CLASS. Never a single
generic "N=2 success rate".
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

TEST_DB_URL = "sqlite:///./backend/data/confit_p2_test.db"
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

# P2-A requires the RAW L2 worker output captured on EVERY
# VTON_LAYER_NOT_APPLIED. The production in-call assertion
# (assert_layer_applied) raises on verify.PASS != True BEFORE the bytes
# return to this probe's capture wrapper. Disable it for this probe only so
# the capture wrapper can read gpu["verify"] + raw bytes directly. The probe
# still reports the engine's verdict honestly from gpu["verify"]. No
# production code is modified (in-process monkeypatch, eval-only probe).
svc.assert_layer_applied = lambda verify, job_id: None

def health():
    return httpx.get(urls[0], headers={"X-VTON-Admin": token}, timeout=60).json()

WORKER = {k: health().get(k) for k in ("model", "device", "git_sha", "service", "ready")}
print("WORKER:", json.dumps(WORKER), flush=True)

OUT = REPO / "evaluation" / "results" / "p2_repeated_matrix"
OUT.mkdir(parents=True, exist_ok=True)

CAPS = []
_real_call = svc.TryOnService._call_gpu_worker

async def capturing_call(self, job_id, person_image, garments,
                         gender_mode="infer_from_image", output_aspect="9:16"):
    cap = {"job_id": job_id}
    try:
        gpu = await _real_call(self, job_id=job_id, person_image=person_image,
                               garments=garments, gender_mode=gender_mode,
                               output_aspect=output_aspect)
        rend = gpu.get("rendered_image_data_url", "")
        raw = base64.b64decode(rend.split(",", 1)[1]) if rend.startswith("data:") else b""
        v = gpu.get("verify") or {}
        cap.update({"ok": True, "sha256": hashlib.sha256(raw).hexdigest() if raw else None,
                    "bytes": len(raw), "PASS": v.get("PASS"),
                    "pixel_change": v.get("metric_pixel_change"),
                    "color_shift": v.get("metric_color_shift"),
                    "execution_time_ms": gpu.get("execution_time_ms")})
        if raw:
            (OUT / f"{job_id}.png").write_bytes(raw)
        CAPS.append(cap)
        return gpu
    except Exception as e:  # noqa: BLE001
        cap.update({"ok": False, "error": str(e)[:300]})
        CAPS.append(cap)
        raise

svc.TryOnService._call_gpu_worker = capturing_call

# sleeve gate capture (LS layers only; production semantics preserved)
CAPTURES = []
CURRENT = None
_real_gate = svc.evaluate_layer_sleeves

async def capturing_gate(*, slot_type, sleeve_length, output_data_url,
                         input_data_url, garment_ref, product_id=None, layer=None):
    cid = CURRENT
    if sleeve_length == "long" and slot_type in ("upper_inner", "upper_outer", "dress"):
        cap = {"layer": layer, "product_id": product_id, "slot_type": slot_type}
        try:
            out_p = OUT / f"{cid}_L{layer}_sleeveout.png"
            in_p = OUT / f"{cid}_L{layer}_sleevein.png"
            gar_p = OUT / f"{cid}_L{layer}_sleevegar.png"
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
        cap0 = CAPTURES[-1] if CAPTURES and CAPTURES[-1].get("product_id") == product_id and sleeve_length == "long" else None
        if cap0 is not None and "decision" not in cap0:
            cap0["gate_status"] = decision.get("status")
            cap0["coverage"] = decision.get("coverage")
    except Exception as e:  # noqa: BLE001
        raised = e
        if CAPTURES and CAPTURES[-1].get("gate_status") is None:
            CAPTURES[-1]["gate_status"] = "REFUSE(raise)"
            CAPTURES[-1]["gate_reason"] = str(e)[:200]
    if raised is not None:
        raise raised
    return decision

svc.evaluate_layer_sleeves = capturing_gate

from PIL import Image

from backend.tests.test_architecture_dynamic import _make_product
from starlette.testclient import TestClient
client = TestClient(app)

FRESH = REPO / "evaluation" / "dyninputs_fresh"
ARCH = REPO / "evaluation" / "archtest_inputs"

def data_url(p: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode()

GAR = {
    "teal":     (ARCH / "garment_rt1.jpg", "tops", "short"),
    "burgundy": (ARCH / "garment_rt4.jpg", "tops", "long"),
    "olive":    (ARCH / "garment_rt2.jpg", "bottoms", "none"),
    "beige":    (FRESH / "garment_beige_chino.jpg", "bottoms", "none"),
    "gray_ls":  (FRESH / "garment_gray_longsleeve.jpg", "tops", "long"),
    "blazer":   (FRESH / "garment_dark_blazer.jpg", "outerwear", "long"),
    "tunic":    (FRESH / "garment_modest_tunic.jpg", "dresses", "long"),
}

db = TestingSessionLocal()
NAVY = None
from backend.app.models.catalog import Product
NAVY = db.query(Product).filter(Product.title == "Pleated Tapered Virgin Wool Trousers").first()
assert NAVY, "navy seed product missing"
db.close()
# navy seed thumbnail is an HTTP URL (catalog-authoritative garment); the
# service fetches + base64-encodes it via the SSRF-protected path, exactly
# as the 36-case matrix ran it.

# static product rows (one per garment, reused for all attempts of the combo)
db = TestingSessionLocal()
PROD = {}
for key, (img, slug, sleeve) in GAR.items():
    PROD[key] = _make_product(db, slug, f"P2 {key}", data_url(img), "#888888", sleeve_length=sleeve)
db.close()

CASES = [
    ("n2tpb_pass", "N2_TP_BOTTOM", "A", [("teal", None), (NAVY, "bottoms")]),
    ("n2tpb_fail", "N2_TP_BOTTOM", "B", [("burgundy", None), ("olive", None)]),
    ("n2io_gray",  "N2_INNER_OUTER", "I", [("gray_ls", None), ("blazer", None)]),
    ("s_top_b",    "SINGLE_TOP", "B", [("burgundy", None)]),
    ("s_top_a",    "SINGLE_TOP", "A", [("teal", None)]),
    ("s_bot_a",    "SINGLE_BOTTOM", "A", [(NAVY, "bottoms")]),
    ("s_ow_i",     "SINGLE_OUTERWEAR", "I", [("blazer", None)]),
    ("s_dress_g",  "SINGLE_DRESS", "G", [("tunic", None)]),
]

PERSONS = {k: (FRESH / f"person_{k}.jpg").read_bytes() for k in "ABG"}
PERSONS["I"] = (FRESH / "person_I.jpg").read_bytes()

RESULTS = {"worker": WORKER, "navy_seed": {"id": NAVY.id, "title": NAVY.title},
           "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "classes": {}}

def run_combo(cid, person_key, items, n=3):
    person_b64 = base64.b64encode(PERSONS[person_key]).decode()
    for att in range(1, n + 1):
        ids = []
        db = TestingSessionLocal()
        try:
            for entry in items:
                if isinstance(entry[0], str):
                    key = entry[0]
                    ids.append(PROD[key])
                else:
                    ids.append(entry[0].id)  # navy seed row
        finally:
            db.close()
        CAPS.clear()
        CAPTURES.clear()
        CURRENT = f"{cid}_a{att}"
        t0 = time.time()
        try:
            r = client.post("/api/v1/tryon/multi-render",
                            json={"product_ids": ids, "user_image_base64": person_b64,
                                  "avatar_model_id": None, "gender_mode": "infer_from_image"})
            j = r.json()
        except Exception:  # noqa: BLE001
            j = {}
        detail = j.get("detail")
        err = detail.get("error", {}) if isinstance(detail, dict) else {}
        layers = []
        for c in CAPS:
            v = c
            layers.append({
                "job_id": c["job_id"], "sha8": str(c.get("sha256"))[:8] if c.get("sha256") else None,
                "PASS": c.get("PASS"), "pixel_change": c.get("pixel_change"),
                "color_shift": c.get("color_shift"), "error": c.get("error"),
                "execution_time_ms": c.get("execution_time_ms"),
            })
        att_rec = {
            "attempt": att, "http": r.status_code if hasattr(r, "status_code") else None,
            "error_code": err.get("code"),
            "layers": layers,
            "sleeve": [dict(c) for c in CAPTURES],
            "elapsed_s": round(time.time() - t0, 1),
        }
        out_url = j.get("rendered_result_url") or j.get("result_image_data_url")
        if isinstance(out_url, str) and out_url.startswith("data:"):
            raw = base64.b64decode(out_url.split(",", 1)[1])
            att_rec["final_sha8"] = hashlib.sha256(raw).hexdigest()[:8]
            (OUT / f"{cid}_a{att}_final.png").write_bytes(raw)
        RESULTS["classes"].setdefault(cid, {"person": person_key,
                                            "garments": [e[0].title if not isinstance(e[0], str) else e[0] for e in items],
                                            "attempts": []})
        RESULTS["classes"][cid]["attempts"].append(att_rec)
        summ = " | ".join(f"L{i+1}:{l['sha8'] or 'ERR'} P={l['PASS']} px={l['pixel_change']}"
                          for i, l in enumerate(layers))
        print(f"{cid:12} a{att} http={att_rec['http']} err={str(att_rec['error_code'])[:26]:26} {summ} {att_rec['elapsed_s']}s",
              flush=True)

for cid, kind, person_key, items in CASES:
    RESULTS["classes"][cid] = {"kind": kind, "person": person_key,
                               "garments": [e[0].title if not isinstance(e[0], str) else e[0] for e in items],
                               "attempts": []}
    run_combo(cid, person_key, items)

RESULTS["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
(OUT / "results.json").write_text(json.dumps(RESULTS, indent=1, default=str))
print("WROTE", OUT / "results.json", flush=True)
