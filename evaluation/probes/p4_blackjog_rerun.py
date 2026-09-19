"""Re-run of the two black_joggers single-bottom cases (KeyError bug fix).

Same production path as p4_fresh_batch_probe.py; writes into the same
results dir under the same case ids (p3a_c_blackjog, p3a_b_blackjog),
appending an 'rerun' marker in results_rerun.json.
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

TEST_DB_URL = "sqlite:///./backend/data/confit_p4_test.db"
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

WORKER = {k: health().get(k) for k in ("model", "device", "git_sha", "service", "ready")}
print("WORKER:", json.dumps(WORKER), flush=True)

OUT = REPO / "evaluation" / "results" / "p4_fresh_batch"
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

from backend.tests.test_architecture_dynamic import _make_product
from starlette.testclient import TestClient
client = TestClient(app)

FRESH = REPO / "evaluation" / "dyninputs_fresh"

def data_url(p: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode()

CASES = [
    ("p3a_c_blackjog", "P3-A", "C", "garment_black_joggers.jpg"),
    ("p3a_b_blackjog", "P3-A", "B", "garment_black_joggers.jpg"),
]

db = TestingSessionLocal()
jog_id = _make_product(db, "bottoms", "P3A black joggers rerun",
                       data_url(FRESH / "garment_black_joggers.jpg"), "#1a1a1a", sleeve_length="none")
db.close()

RESULTS = {"worker": WORKER, "note": "rerun after KeyError fix; same case ids as first batch",
           "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "cases": {}}

for cid, kind, person_key, gfile in CASES:
    CAPS.clear()
    person = base64.b64encode((FRESH / f"person_{person_key}.jpg").read_bytes()).decode()
    t0 = time.time()
    r = client.post("/api/v1/tryon/multi-render",
                    json={"product_ids": [jog_id], "user_image_base64": person,
                          "avatar_model_id": None, "gender_mode": "infer_from_image"})
    j = r.json()
    detail = j.get("detail")
    err = detail.get("error", {}) if isinstance(detail, dict) else {}
    entry = {"http": r.status_code, "elapsed_s": round(time.time() - t0, 1),
             "error_code": err.get("code"), "error_message": str(err.get("message", ""))[:250],
             "layers": [dict(c) for c in CAPS]}
    out_url = j.get("rendered_result_url") or j.get("result_image_data_url")
    if isinstance(out_url, str) and out_url.startswith("data:"):
        raw = base64.b64decode(out_url.split(",", 1)[1])
        entry["final_sha256"] = hashlib.sha256(raw).hexdigest()
        (OUT / f"{cid}_final.png").write_bytes(raw)
    RESULTS["cases"][cid] = entry
    v = CAPS[0] if CAPS else {}
    print(f"{cid} http={r.status_code} err={str(entry['error_code'])[:26]:26} "
          f"sha={str(v.get('sha256'))[:8]} P={v.get('PASS')} px={v.get('pixel_change')} "
          f"cs={v.get('color_shift')} {entry['elapsed_s']}s", flush=True)

RESULTS["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
(OUT / "results_rerun.json").write_text(json.dumps(RESULTS, indent=1, default=str))
print("WROTE", OUT / "results_rerun.json", flush=True)
