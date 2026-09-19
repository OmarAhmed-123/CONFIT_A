"""P0 Phase-4 controlled N=2 repeated-run study (2026-09-16).

ONE fixed logical request, repeated N times:
  person_A.jpg (fixed bytes) + garment_rt1 teal tee (fixed bytes) +
  garment_rt2 olive chino (fixed bytes), SAME catalog IDs across all
  attempts, same server-derived order, same production worker endpoint.

Records per attempt: attempt id, job ids, worker revision/model/device,
L1 output sha + dims + L1 verify (quality metrics), L2 output sha (when
present), L2 result, L2 pixel_change, L2 color_shift, final failure code,
timestamps, elapsed. Raw L1/L2/final worker bytes are saved as .png
artifacts (never into the JSON record — P8 record hygiene).

Purpose: estimate the frequency of each distinct L1 output class and test
whether L1 sample identity deterministically predicts the L2 outcome.
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
print("WORKER_START:", json.dumps({k: WORKER_START.get(k) for k in ("model", "device", "git_sha", "service", "ready")}), flush=True)

OUT = REPO / "evaluation" / "results" / "p0_repeated_runs"
OUT.mkdir(parents=True, exist_ok=True)

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
        cap["model_used"] = gpu.get("model_used")
        cap["execution_time_ms"] = gpu.get("execution_time_ms")
        # persist raw worker bytes as artifact (NOT into JSON)
        if raw:
            (OUT / f"{job_id}.png").write_bytes(raw)
        CAPS.append(cap)
        return gpu
    except Exception as e:  # noqa: BLE001
        cap["ok"] = False
        cap["error"] = str(e)[:300]
        CAPS.append(cap)
        raise

svc.TryOnService._call_gpu_worker = capturing_call

from backend.tests.test_architecture_dynamic import _make_product
from starlette.testclient import TestClient
client = TestClient(app)

FRESH = REPO / "evaluation" / "dyninputs_fresh"
ARCH = REPO / "evaluation" / "archtest_inputs"

def data_url(p: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode()

# ONE pair of catalog rows, reused for every attempt (same IDs)
db = TestingSessionLocal()
top_id = _make_product(db, "tops", "P0 fixed teal tee", data_url(ARCH / "garment_rt1.jpg"), "#2E7F8F", sleeve_length="short")
bottom_id = _make_product(db, "bottoms", "P0 fixed olive chino", data_url(ARCH / "garment_rt2.jpg"), "#6B6B3D", sleeve_length="none")
db.close()
print(f"fixed catalog ids: top={top_id} bottom={bottom_id}", flush=True)

PERSON_B64 = base64.b64encode((FRESH / "person_A.jpg").read_bytes()).decode()
PERSON_SHA = hashlib.sha256((FRESH / "person_A.jpg").read_bytes()).hexdigest()
TOP_SHA = hashlib.sha256((ARCH / "garment_rt1.jpg").read_bytes()).hexdigest()
BOTTOM_SHA = hashlib.sha256((ARCH / "garment_rt2.jpg").read_bytes()).hexdigest()

N = int(os.environ.get("P0_N", "30"))
RESULTS = {
    "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "worker_start": {k: WORKER_START.get(k) for k in ("model", "device", "git_sha", "service", "ready")},
    "request": {"person_sha256": PERSON_SHA, "top_sha256": TOP_SHA, "bottom_sha256": BOTTOM_SHA,
                "top_id": top_id, "bottom_id": bottom_id, "product_ids": [top_id, bottom_id]},
    "attempts": [],
}

for i in range(1, N + 1):
    CAPS.clear()
    t0 = time.time()
    try:
        r = client.post("/api/v1/tryon/multi-render",
                        json={"product_ids": [top_id, bottom_id],
                              "user_image_base64": PERSON_B64,
                              "avatar_model_id": None,
                              "gender_mode": "infer_from_image"})
        j = r.json()
    except Exception as ex:  # noqa: BLE001
        j = {}
    detail = j.get("detail")
    err = detail.get("error", {}) if isinstance(detail, dict) else {}
    l1 = [c for c in CAPS if c["job_id"].endswith("_l1")]
    l2 = [c for c in CAPS if c["job_id"].endswith("_l2")]
    att = {
        "attempt": i,
        "t_start": time.strftime("%H:%M:%S"),
        "elapsed_s": round(time.time() - t0, 1),
        "http": r.status_code if hasattr(r, "status_code") else None,
        "error_code": err.get("code"),
        "layer1": {
            "job_id": l1[0]["job_id"] if l1 else None,
            "sha256": l1[0].get("rendered_sha256") if l1 else None,
            "bytes": l1[0].get("rendered_bytes") if l1 else None,
            "verify": l1[0].get("verify") if l1 else None,
            "model_used": l1[0].get("model_used") if l1 else None,
            "execution_time_ms": l1[0].get("execution_time_ms") if l1 else None,
        } if l1 else None,
        "layer2": {
            "job_id": l2[0]["job_id"] if l2 else None,
            "sha256": l2[0].get("rendered_sha256") if l2 else None,
            "bytes": l2[0].get("rendered_bytes") if l2 else None,
            "verify": l2[0].get("verify") if l2 else None,
            "execution_time_ms": l2[0].get("execution_time_ms") if l2 else None,
            "error": l2[0].get("error") if l2 else None,
        } if l2 else None,
        "l1_error": l1[0].get("error") if l1 and not l1[0].get("ok") else None,
    }
    out_url = j.get("rendered_result_url") or j.get("result_image_data_url")
    if isinstance(out_url, str) and out_url.startswith("data:"):
        raw = base64.b64decode(out_url.split(",", 1)[1])
        att["final_sha256"] = hashlib.sha256(raw).hexdigest()
        (OUT / f"attempt_{i:02d}_final.png").write_bytes(raw)
    RESULTS["attempts"].append(att)
    v = att["layer2"]["verify"] if att["layer2"] else None
    print(f"a{i:02d} http={att['http']} l1={str(att['layer1']['sha256'])[:8] if att['layer1'] else '-'} "
          f"l2px={v['metric_pixel_change'] if v else '-'} err={att['error_code'] or '-'} {att['elapsed_s']}s", flush=True)

WORKER_END = health()
RESULTS["worker_end"] = {k: WORKER_END.get(k) for k in ("git_sha", "ready", "device")}
RESULTS["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")

(OUT / "attempts.json").write_text(json.dumps(RESULTS, indent=1, default=str))
print("WROTE", OUT / "attempts.json", flush=True)
