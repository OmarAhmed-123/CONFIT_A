"""P0-B: same L1 bytes -> multiple L2 runs (direct worker calls, no L1 regen).

For every distinct L1 output class observed in the P0 30-attempt sequence
(evaluation/results/p0_repeated_runs/), this probe re-runs ONLY the L2
stage directly against the production worker:

  R1, R2 : exact L1 bytes (worker PNG data URL, byte-for-byte)
  R3     : same L1 content re-encoded JPEG q92
  R4     : same L1 content re-encoded JPEG q95
  R5     : same L1 content re-encoded JPEG q88

Hypothesis A (L1 image content decisive) vs Hypothesis B (independent
L2 stochastic component) are separated as follows:
  * R1 vs R2 identical bytes  -> worker cache/determinism at the L2 stage
  * R1 vs R3/R4/R5 same image, different bytes -> byte-identity vs content
  * class with P0-L2-fail vs class with P0-L2-pass, both repeated
    -> content-level decisiveness

Each run records: L2 sha256, worker verify (PASS/pixel_change/color_shift),
execution time, and whether the L2 bytes equal the L2 bytes the P0 sequence
already produced for the same L1 class (cache-hit fingerprint). Raw L2
outputs are saved as artifacts (P2-A: raw L2 captured on EVERY result);
the JSON record holds hashes + metrics only (P8).

No production code is modified; the app's quality gates are NOT involved
(we call _call_gpu_worker directly and read the worker's own verify block).
"""
import asyncio
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
import io
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.database import get_db, engine as app_engine
from backend.app.seed_data import seed_database
from backend.app.main import app

TEST_DB_URL = "sqlite:///./backend/data/confit_p0b_test.db"
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

# This probe calls the worker DIRECTLY and reads the worker's own verify
# block + raw output bytes. The production in-call assertion
# (assert_layer_applied) raises on verify.PASS != True BEFORE returning the
# bytes, which would block the raw-L2-on-not-applied capture. Disable it for
# this probe only; the gate's decision is read straight from gpu["verify"].
# No production code is modified (in-process monkeypatch, eval-only probe).
svc.assert_layer_applied = lambda verify, job_id: None

def health():
    return httpx.get(urls[0], headers={"X-VTON-Admin": token}, timeout=60).json()

WORKER = {k: health().get(k) for k in ("model", "device", "git_sha", "service", "ready")}
print("WORKER:", json.dumps(WORKER), flush=True)

P0DIR = REPO / "evaluation" / "results" / "p0_repeated_runs"
OUT = REPO / "evaluation" / "results" / "p0b_same_l1_repeats"
OUT.mkdir(parents=True, exist_ok=True)

data = json.loads((P0DIR / "attempts.json").read_text())
attempts = data["attempts"]

# distinct L1 classes -> first artifact file + the L2 outcomes P0 already saw
classes = {}
for a in attempts:
    l1 = a.get("layer1")
    if not l1 or not l1.get("sha256") or not l1.get("job_id"):
        continue
    sha8 = l1["sha256"][:8]
    if sha8 not in classes:
        classes[sha8] = {"full_sha": l1["sha256"], "artifact": P0DIR / f"{l1['job_id']}.png",
                         "p0_l2": []}
    l2 = a.get("layer2")
    v = (l2 or {}).get("verify") if l2 else None
    classes[sha8]["p0_l2"].append({
        "attempt": a["attempt"],
        "l2_sha8": (l2 or {}).get("sha256", "")[:8] if l2 and l2.get("sha256") else None,
        "PASS": v.get("PASS") if v else None,
        "pixel_change": (v or {}).get("metric_pixel_change") if v else None,
    })

print(f"distinct L1 classes from P0: {list(classes.keys())}", flush=True)

# bottom garment (olive chino) — same file the P0 request used
ARCH = REPO / "evaluation" / "archtest_inputs"
BOTTOM_B64 = "data:image/jpeg;base64," + base64.b64encode((ARCH / "garment_rt2.jpg").read_bytes()).decode()

db = TestingSessionLocal()
service = svc.TryOnService(db)

async def direct_l2(tag: str, person_data_url: str) -> dict:
    t0 = time.time()
    rec = {"tag": tag, "t": time.strftime("%H:%M:%S"),
           "person_sha256": hashlib.sha256(base64.b64decode(person_data_url.split(",", 1)[1])).hexdigest()}
    try:
        gpu = await service._call_gpu_worker(
            job_id=f"p0b_{tag}",
            person_image=person_data_url,
            garments=[{"image_base64": BOTTOM_B64, "slot_type": "lower",
                       "sleeve_length": "none", "product_id": None,
                       "title": "P0B olive chino"}],
            gender_mode="infer_from_image",
            output_aspect="9:16",
        )
        rend = gpu.get("rendered_image_data_url", "")
        raw = base64.b64decode(rend.split(",", 1)[1]) if rend.startswith("data:") else b""
        v = gpu.get("verify") or {}
        rec.update({
            "ok": True,
            "l2_sha256": hashlib.sha256(raw).hexdigest(),
            "l2_bytes": len(raw),
            "PASS": v.get("PASS"),
            "pixel_change": v.get("metric_pixel_change"),
            "color_shift": v.get("metric_color_shift"),
            "execution_time_ms": gpu.get("execution_time_ms"),
        })
        if raw:
            (OUT / f"{tag}_l2.png").write_bytes(raw)
    except Exception as e:  # noqa: BLE001
        rec.update({"ok": False, "error": str(e)[:300]})
    rec["elapsed_s"] = round(time.time() - t0, 1)
    return rec

def png_data_url(raw: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(raw).decode()

def jpeg_data_url(raw_png: bytes, q: int) -> str:
    im = Image.open(io.BytesIO(raw_png)).convert("RGB")
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=q)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

RESULTS = {"worker": WORKER, "bottom_sha256": hashlib.sha256(BOTTOM_B64.encode()).hexdigest(),
           "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "classes": {}}

for sha8, info in classes.items():
    raw = info["artifact"].read_bytes()
    fmt = "PNG" if raw[:4] == b"\x89PNG" else ("JPEG" if raw[:2] == b"\xff\xd8" else "UNKNOWN")
    cls_rec = {"full_sha": info["full_sha"], "artifact_fmt": fmt,
               "artifact_sha256": hashlib.sha256(raw).hexdigest(),
               "p0_l2_outcomes": info["p0_l2"], "runs": []}
    exact = f"data:{'image/png' if fmt == 'PNG' else 'image/jpeg'};base64," + base64.b64encode(raw).decode()
    plan = [("R1_exact", exact), ("R2_exact", exact),
            ("R3_q92", jpeg_data_url(raw, 92)),
            ("R4_q95", jpeg_data_url(raw, 95)),
            ("R5_q88", jpeg_data_url(raw, 88))]
    for tag, du in plan:
        rec = asyncio.run(direct_l2(f"{sha8}_{tag}", du))
        # cache-hit fingerprint vs P0's L2 for this L1 class
        rec["p0_l2_match"] = [p["attempt"] for p in info["p0_l2"]
                              if p["l2_sha8"] and p["l2_sha8"] == rec.get("l2_sha256", "")[:8]]
        cls_rec["runs"].append(rec)
        print(f"L1={sha8} {tag:9} ok={rec['ok']} PASS={rec.get('PASS')} "
              f"px={rec.get('pixel_change')} sha={str(rec.get('l2_sha256'))[:8]} p0match={rec['p0_l2_match']} "
              f"{rec['elapsed_s']}s", flush=True)
    RESULTS["classes"][sha8] = cls_rec

RESULTS["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
(OUT / "p0b_results.json").write_text(json.dumps(RESULTS, indent=1, default=str))
print("WROTE", OUT / "p0b_results.json", flush=True)
