"""N=2 top+bottom failure isolation probe (Phase 3, 2026-09-16).

Answers: why does N=2 layer-2 (bottom) application succeed for some runtime
inputs and fail for others, and what is the first measurable divergence?

P0: controlled matrix — 4 persons (A, B, C, fresh I) x 3 tops (teal short
    tee T1, burgundy long-sleeve T2, fresh rust long-sleeve T3) x 3 bottoms
    (olive chino B1, catalog navy trousers B2, fresh beige chino B3) = 36
    combinations, all through the production path (TestClient ->
    TryOnService -> live worker). Every catalog row is fresh per case.
P1: per-layer boundary capture via a wrapper on TryOnService._call_gpu_worker
    (production semantics preserved; wrapper only records): layer job id,
    person-image hash/dims/mode, garment payload (slot, sleeve_length, image
    hash/dims), wall timing, worker verify metrics (PASS, pixel_change,
    color_shift, stddev), model/execution metadata, rendered hash/dims.
P2/P3: one-variable + determinism re-runs of one failing and one passing
    combination (x3 each), a delayed re-run, and a fresh-catalog-row re-run
    (same image bytes, new product row).
P4: forensic raw layer-2 re-render — for every case where layer 2 did not
    complete normally, the captured layer-1 output + exact layer-2 garment
    payload are POSTed directly to the worker (identical request shape, new
    job id) to obtain the RAW layer-2 output + verify metrics independent of
    the backend gate. Recorded as a separate worker job (fresh diffusion
    seed); it is forensics, not a production path.

NO production code is modified. NO gate is bypassed. NO threshold changes.
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

import backend.app.services.tryon_service as svc

def health():
    return httpx.get(urls[0], headers={"X-VTON-Admin": token}, timeout=60).json()

WORKER_START = health()
print("WORKER:", json.dumps({k: WORKER_START.get(k) for k in ("model", "device", "git_sha", "service", "ready")}), flush=True)

# --- P1 boundary capture wrapper (record-only) --------------------------------
CAPS = []
_real_call = svc.TryOnService._call_gpu_worker

def _b64_info(b64: str):
    try:
        raw = base64.b64decode(b64.split(",", 1)[1] if "," in b64 else b64)
        im = Image.open(__import__("io").BytesIO(raw))
        return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
                "size": list(im.size), "mode": im.mode}
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {str(e)[:120]}"}

async def capturing_call(self, job_id, person_image, garments,
                         gender_mode="infer_from_image", output_aspect="9:16"):
    cap = {
        "job_id": job_id,
        "t_start": time.time(),
        "person": _b64_info(person_image),
        "person_kind": "data_url" if person_image.startswith("data:") else person_image[:64],
        "garments": [{
            "product_id": g.get("product_id"),
            "slot_type": g.get("slot_type"),
            "sleeve_length": g.get("sleeve_length"),
            "image_kind": "base64" if g.get("image_base64") else "url",
            "image_sha256": _b64_info(g["image_base64"])["sha256"] if g.get("image_base64") else None,
            "image_url": g.get("image_url"),
        } for g in garments],
        "gender_mode": gender_mode,
        "output_aspect": output_aspect,
    }
    try:
        gpu = await _real_call(self, job_id=job_id, person_image=person_image,
                               garments=garments, gender_mode=gender_mode,
                               output_aspect=output_aspect)
        cap["ok"] = True
        cap["elapsed_s"] = round(time.time() - cap["t_start"], 1)
        cap["rendered"] = _b64_info(gpu.get("rendered_image_data_url", ""))
        cap["verify"] = gpu.get("verify")
        cap["model_used"] = gpu.get("model_used")
        cap["execution_time_ms"] = gpu.get("execution_time_ms")
        cap["layers_processed"] = gpu.get("layers_processed")
        CAPS.append(cap)
        return gpu
    except Exception as e:  # noqa: BLE001
        cap["ok"] = False
        cap["elapsed_s"] = round(time.time() - cap["t_start"], 1)
        cap["error"] = str(e)[:400]
        CAPS.append(cap)
        raise

svc.TryOnService._call_gpu_worker = capturing_call

# --- inputs --------------------------------------------------------------------
FRESH = REPO / "evaluation" / "dyninputs_fresh"
ARCH = REPO / "evaluation" / "archtest_inputs"
OUT = REPO / "evaluation" / "results" / "n2_isolation"
OUT.mkdir(parents=True, exist_ok=True)

def b64(p: Path) -> str:
    return base64.b64encode(p.read_bytes()).decode()

PERSONS = {"A": FRESH / "person_A.jpg", "B": FRESH / "person_B.jpg",
           "C": FRESH / "person_C.jpg", "I": FRESH / "person_I.jpg"}
TOPS = {  # key: (image, slug, title, hex, sleeve_length)
    "T1": (ARCH / "garment_rt1.jpg", "tops", "N2I teal tee", "#2E7F8F", "short"),
    "T2": (ARCH / "garment_rt4.jpg", "tops", "N2I burgundy LS", "#6E2233", "long"),
    "T3": (FRESH / "garment_rust_longsleeve.jpg", "tops", "N2I fresh rust LS", "#A0522D", "long"),
}
BOTTOMS = {
    "B1": (ARCH / "garment_rt2.jpg", "bottoms", "N2I olive chino", "#6B6B3D", "none"),
    "B3": (FRESH / "garment_beige_chino.jpg", "bottoms", "N2I fresh beige chino", "#D8C8A8", "none"),
}

from backend.app.models.catalog import Product
_db = TestingSessionLocal()
NAVY = _db.query(Product).filter(
    Product.title == "Pleated Tapered Virgin Wool Trousers").first()
assert NAVY, "seed navy trousers product missing"
_db.close()
print("navy seed product:", NAVY.id, "sleeve:", NAVY.sleeve_length, "img:", NAVY.thumbnail_url[:80])

def data_url(p: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode()

from backend.tests.test_architecture_dynamic import _make_product
from starlette.testclient import TestClient
client = TestClient(app)

def make_row(db, tag, img, slug, title, hex_, sleeve):
    return _make_product(db, slug, title, data_url(img), hex_, sleeve_length=sleeve)

def run_case(tag, person_key, top_key, bottom_key, fresh_rows=True):
    db = TestingSessionLocal()
    try:
        t_img, t_slug, t_title, t_hex, t_sleeve = TOPS[top_key]
        if bottom_key == "B2":
            bottom_id = NAVY.id
        else:
            b_img, b_slug, b_title, b_hex, b_sleeve = BOTTOMS[bottom_key]
            bottom_id = make_row(db, tag, b_img, b_slug, b_title, b_hex, b_sleeve)
        top_id = make_row(db, tag, t_img, t_slug, t_title, t_hex, t_sleeve)
    finally:
        db.close()
    CAPS.clear()
    t0 = time.time()
    r = client.post("/api/v1/tryon/multi-render",
                    json={"product_ids": [top_id, bottom_id],
                          "user_image_base64": b64(PERSONS[person_key]),
                          "avatar_model_id": None,
                          "gender_mode": "infer_from_image"})
    elapsed = round(time.time() - t0, 1)
    try:
        j = r.json()
    except Exception:  # noqa: BLE001
        j = {}
    detail = j.get("detail")
    err = detail.get("error", {}) if isinstance(detail, dict) else {}
    entry = {
        "tag": tag, "person": person_key, "top": top_key, "bottom": bottom_key,
        "product_ids": {"top": top_id, "bottom": bottom_id, "navy_seed": NAVY.id},
        "http": r.status_code, "elapsed_s": elapsed,
        "status": j.get("status"),
        "error_code": err.get("code"),
        "error_message": str(err.get("message", ""))[:300],
        "layering_order": j.get("layering_order"),
        "verification": j.get("verification"),
        # copy: CAPS is cleared at the start of the next case (aliasing bug
        # found 2026-09-16: first run's matrix.json "layers" fields all
        # pointed at the last case; per-case prints/forensics/PNGs unaffected)
        "layers": [dict(c) for c in CAPS],
    }
    out_url = j.get("rendered_result_url") or j.get("result_image_data_url")
    if isinstance(out_url, str) and out_url.startswith("data:"):
        entry["final_sha256"] = _b64_info(out_url)["sha256"]
        (OUT / f"{tag}_final.png").write_bytes(base64.b64decode(out_url.split(",", 1)[1]))
    return entry

# --- P4 forensic raw layer-2 re-render -----------------------------------------
def forensic_l2(tag, rendered_b64: str, payload: dict):
    """POST the captured layer-1 output + exact layer-2 garment payload
    directly to the worker (identical request shape, fresh job id)."""
    if not (rendered_b64 and payload):
        return {"error": "missing captured L1 output or L2 payload"}
    headers = {"X-VTON-Admin": token}
    t0 = time.time()
    resp = httpx.post(urls[1], headers=headers, timeout=120, json={
        "job_id": f"n2i_{tag}_forensic_l2",
        "user_image_base64_or_url": rendered_b64,
        "garments": [payload],
        "gender_mode": "infer_from_image",
        "output_aspect": "9:16",
    })
    elapsed = round(time.time() - t0, 1)
    out = {"http": resp.status_code, "elapsed_s": elapsed}
    if resp.status_code == 200:
        gj = resp.json()
        out["verify"] = gj.get("verify")
        out["model_used"] = gj.get("model_used")
        out["execution_time_ms"] = gj.get("execution_time_ms")
        rend = gj.get("rendered_image_data_url", "")
        if rend.startswith("data:"):
            out["rendered"] = _b64_info(rend)
            (OUT / f"{tag}_forensic_L2.png").write_bytes(
                base64.b64decode(rend.split(",", 1)[1]))
    else:
        out["body"] = resp.text[:300]
    return out

# stash rendered b64 + garment payload IN MEMORY ONLY for forensics. Persisted
# records must NOT contain image bytes (P14: test_no_image_data_in_run_records)
# — serialized "layers" entries carry only shas/sizes.
_MEM_RENDERED = {}   # job_id -> rendered data-url
_MEM_PAYLOAD = {}    # job_id -> garment payload dict (has image_base64)

async def stashing_call(self, job_id, person_image, garments,
                        gender_mode="infer_from_image", output_aspect="9:16"):
    try:
        gpu = await capturing_call(self, job_id, person_image, garments,
                                   gender_mode, output_aspect)
        cap = CAPS[-1]
        g0 = garments[0] if garments else None
        cap["_payload_sha256"] = g0.get("image_sha256") if g0 else None
        if g0:
            _MEM_PAYLOAD[job_id] = g0
        if cap.get("ok"):
            rend = gpu.get("rendered_image_data_url", "")
            if rend.startswith("data:"):
                _MEM_RENDERED[job_id] = rend
                try:
                    (OUT / f"{job_id.replace('multi_', '')}.png").write_bytes(
                        base64.b64decode(rend.split(",", 1)[1]))
                except Exception:  # noqa: BLE001
                    pass
        return gpu
    except Exception:
        if garments:
            _MEM_PAYLOAD[job_id] = garments[0]
        raise

svc.TryOnService._call_gpu_worker = stashing_call

# --- P0 matrix -----------------------------------------------------------------
RESULTS = {
    "worker": {k: WORKER_START.get(k) for k in ("model", "device", "git_sha", "service", "ready")},
    "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "navy_seed_product": {"id": NAVY.id, "title": NAVY.title,
                          "thumbnail": NAVY.thumbnail_url[:120], "sleeve": NAVY.sleeve_length},
    "cases": {},
}

MATRIX_P = ["A", "B", "C", "I"]
MATRIX_T = ["T1", "T2", "T3"]
MATRIX_B = ["B1", "B2", "B3"]

SMOKE = "--smoke" in sys.argv
for p in MATRIX_P:
    for t in MATRIX_T:
        for b in MATRIX_B:
            tag = f"n2_{p}_{t}_{b}"
            if SMOKE and tag != "n2_A_T1_B1":
                continue
            try:
                e = run_case(tag, p, t, b)
            except Exception as ex:  # noqa: BLE001
                e = {"tag": tag, "person": p, "top": t, "bottom": b,
                     "http": None, "error": f"{type(ex).__name__}: {str(ex)[:200]}"}
            RESULTS["cases"][tag] = e
            l2 = [c for c in e.get("layers", []) if c.get("job_id", "").endswith("_l2")]
            v = l2[0].get("verify") if l2 else None
            fs = "F" if e.get("error_code") == "VTON_LAYER_NOT_APPLIED" else ""
            print(f"{tag:10} http={e.get('http')} err={str(e.get('error_code'))[:26]:26} "
                  f"L2verify={json.dumps(v) if v else '-'} {fs}", flush=True)
            # P4 forensic for any case where L2 did not complete normally
            l1 = [c for c in e.get("layers", []) if c.get("job_id", "").endswith("_l1")]
            if l2 and not (l2[0].get("ok")) and l1 and l1[0].get("ok"):
                fore = forensic_l2(tag,
                                   _MEM_RENDERED.get(l1[0].get("job_id")),
                                   _MEM_PAYLOAD.get(l2[0].get("job_id")))
                e["forensic_l2"] = fore
                fv = fore.get("verify")
                print(f"   forensic L2: http={fore.get('http')} verify={json.dumps(fv) if fv else fore.get('error')}", flush=True)

WORKER_END = health()
RESULTS["worker_end"] = {k: WORKER_END.get(k) for k in ("git_sha", "ready")}

(OUT / "matrix.json").write_text(json.dumps(RESULTS, indent=1, default=str))
print("WROTE", OUT / "matrix.json", flush=True)
