"""P1 Phase-5: N=2 controlled experiments (production path, live worker).

Six controlled conditions, each a fresh job (no retries; the only repeated
runs are the explicit controlled repeats this experiment defines):

  C1  SAME L1 + SAME BOTTOM      (A, rt1, olive) x5, spaced 90 s apart
  C4  SAME INPUT ACROSS TIME     = the same C1 sequence (spaced 90 s)
  C2  SAME L1 + DIFF BOTTOM      (A, rt1, navy) x3 ; (A, rt1, beige) x3
  C3  SAME PERSON/TOP + NEW L1   (A, rt4, olive) x3  (rt4 = different top
                                                 -> different L1 sample)
  C5  MULTI-PERSON SAME BOTTOM   (C, rt1, navy) x2 ; (I, rt1, navy) x2
  C6  MULTI-BOTTOM SAME L1       (A, rt1, black-joggers) x2

rt1 is a SHORT-sleeve top so the (long-sleeve-only) v2.3 sleeve gate is
N/A and the experiment isolates the N=2 LAYER-APPLICATION variable.
Anchor (A, rt1) produces a deterministic L1 byte-sample (0f29f3a5) per
Phase 3, so "same L1" is genuinely fixed L1 bytes, not just same inputs.

Per run records: worker git revision, sha256 of each input (person/top/
bottom), L1 sha256 + bytes, L2 sha256 + bytes, L2 verify metrics, HTTP
decision + canonical error code, elapsed. Raw L1/L2 bytes saved (eval
synthetic persons; no user PII).
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

TEST_DB_URL = "sqlite:///./backend/data/confit_p1_test.db"
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
        rend = gpu.get("rendered_image_data_url", "")
        raw = base64.b64decode(rend.split(",", 1)[1]) if rend.startswith("data:") else b""
        cap.update(ok=True, sha256=hashlib.sha256(raw).hexdigest(),
                   bytes=len(raw), verify=gpu.get("verify"), raw=raw)
        CAPS.append(cap)
        return gpu
    except Exception as e:  # noqa: BLE001
        cap.update(ok=False, error=str(e)[:220])
        CAPS.append(cap)
        raise

svc.TryOnService._call_gpu_worker = capturing_call

from backend.app.models.catalog import Product
from backend.tests.test_architecture_dynamic import _make_product
from starlette.testclient import TestClient
client = TestClient(app)

FRESH = REPO / "evaluation" / "dyninputs_fresh"
ARCH = REPO / "evaluation" / "archtest_inputs"
OUT = REPO / "evaluation" / "results" / "p1_n2_controlled"
OUT.mkdir(parents=True, exist_ok=True)

def sha8(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:8]

PERSONS = {k: (FRESH / f"person_{k}.jpg").read_bytes() for k in ("A", "C", "I")}
TOPS = {"rt1": ARCH / "garment_rt1.jpg", "rt4": ARCH / "garment_rt4.jpg"}
BOTTOMS = {
    "olive": ARCH / "garment_rt2.jpg",
    "beige": FRESH / "garment_beige_chino.jpg",
    "blackjog": FRESH / "garment_black_joggers.jpg",
}

_db = TestingSessionLocal()
NAVY = _db.query(Product).filter(
    Product.title == "Pleated Tapered Virgin Wool Trousers").first()
_db.close()

def data_url(b: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(b).decode()

def render(person_key, top_key, bottom_key, bottom_is_navy=False, tag=None):
    db = TestingSessionLocal()
    try:
        if bottom_is_navy:
            bottom_id = NAVY.id
            bottom_bytes = b"<catalog-navy-trousers>"
        else:
            bp = BOTTOMS[bottom_key]
            bottom_id = _make_product(db, f"n2_{bottom_key}", f"P1 {bottom_key}",
                                      data_url(bp.read_bytes()), "#888888",
                                      sleeve_length="none")
            bottom_bytes = bp.read_bytes()
        tp = TOPS[top_key]
        top_id = _make_product(db, f"n2_{top_key}", f"P1 {top_key}",
                               data_url(tp.read_bytes()), "#2E7F8F", sleeve_length="short")
    finally:
        db.close()
    CAPS.clear()
    t0 = time.time()
    try:
        r = client.post("/api/v1/tryon/multi-render",
                        json={"product_ids": [top_id, bottom_id],
                              "user_image_base64": base64.b64encode(PERSONS[person_key]).decode(),
                              "avatar_model_id": None, "gender_mode": "infer_from_image"})
        j = r.json()
        http = r.status_code
    except Exception as e:  # noqa: BLE001
        j, http = {}, f"EXC:{type(e).__name__}"
    err = (j.get("detail") or {}).get("error", {}) if isinstance(j.get("detail"), dict) else {}
    l1 = [c for c in CAPS if c["job_id"].endswith("_l1")]
    l2 = [c for c in CAPS if c["job_id"].endswith("_l2")]
    l1c, l2c = (l1[0] if l1 else {}), (l2[0] if l2 else {})
    rec = {
        "person": person_key, "top": top_key, "bottom": bottom_key,
        "input_sha8": {"person": sha8(PERSONS[person_key]),
                       "top": sha8(TOPS[top_key].read_bytes()),
                       "bottom": sha8(bottom_bytes)},
        "http": http,
        "error_code": err.get("code"),
        "l1_sha8": l1c.get("sha256", "")[:8] if l1c.get("sha256") else None,
        "l1_bytes": l1c.get("bytes"),
        "l2_sha8": l2c.get("sha256", "")[:8] if l2c.get("sha256") else None,
        "l2_bytes": l2c.get("bytes"),
        "l2_verify": l2c.get("verify"),
        "l2_error": l2c.get("error"),
        "elapsed_s": round(time.time() - t0, 1),
    }
    # save raw L1/L2 bytes (eval synthetic persons; no user PII)
    tag = tag or f"{person_key}_{top_key}_{bottom_key}"
    for layer, cap in (("l1", l1c), ("l2", l2c)):
        if cap.get("raw"):
            (OUT / f"raw_{tag}_{layer}.png").write_bytes(cap["raw"])
            rec[f"{layer}_saved"] = f"raw_{tag}_{layer}.png"
    return rec

WORKER = {k: httpx.get(urls[0], headers={"X-VTON-Admin": token}, timeout=60).json().get(k)
          for k in ("model", "device", "git_sha", "service", "ready")}
print("WORKER:", json.dumps(WORKER), flush=True)

RESULTS = {"worker": WORKER, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "runs": []}

def run(cond, cid, person, top, bottom, navy=False):
    rec = render(person, top, bottom, navy, tag=cid)
    rec.update(condition=cond, id=cid, t=time.strftime("%H:%M:%S"))
    RESULTS["runs"].append(rec)
    print(f"[{cond}] {cid} {person}/{top}/{bottom} http={rec['http']} "
          f"code={str(rec['error_code'])[:28]} l1={rec['l1_sha8']} l2={rec['l2_sha8']} "
          f"l2v={str(rec['l2_verify'])[:40]} {rec['elapsed_s']}s", flush=True)
    return rec

# C1 + C4: (A, rt1, olive) x5 spaced 90s
for i in range(1, 6):
    run("C1+4", f"C1-{i}", "A", "rt1", "olive")
    if i < 5:
        print(f"  ... sleeping 90 s (time axis) ...", flush=True)
        time.sleep(90)

# C2: same L1 (A,rt1), different bottoms
for i in (1, 2, 3):
    run("C2", f"C2-navy-{i}", "A", "rt1", "navy", navy=True)
    run("C2", f"C2-beige-{i}", "A", "rt1", "beige")

# C3: same person A, different top rt4 -> new L1, same bottom olive
for i in (1, 2, 3):
    run("C3", f"C3-{i}", "A", "rt4", "olive")

# C5: multi-person, same bottom navy
for p in ("C", "I"):
    for i in (1, 2):
        run("C5", f"C5-{p}{i}", p, "rt1", "navy", navy=True)

# C6: multi-bottom, same L1 (A,rt1), black joggers
for i in (1, 2):
    run("C6", f"C6-{i}", "A", "rt1", "blackjog")

RESULTS["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
(OUT / "results.json").write_text(json.dumps(RESULTS, indent=1, default=str))
print("WROTE", OUT / "results.json", flush=True)
