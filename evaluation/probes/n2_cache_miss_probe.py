"""N=2 worker-cache / diffusion-sampling controlled test (Phase 3, 2026-09-16).

Context: the N=2 matrix + determinism runs showed byte-identical layer
outputs across repeated calls with identical input bytes (worker output
caching), plus at least one cache miss producing a different sample
(D3-2, sha 00dac3120b9b vs 0f29f3a547fe, same A+teal input).

Question (controlled): is the layer-2 bottom NON-application (A+teal+olive,
pixel_change 0.2407) a robust property of the (L1 bytes, bottom) input
combination, or a sampling artifact of one cached diffusion sample?

Method: take the captured L1 output (A+teal, sha 0f29f3a547fe), re-encode it
as JPEG at 3 different qualities (different bytes => fresh worker sample,
same visual content), and POST each as a direct worker L2 job with the exact
olive-chino payload. 3 fresh samples of the same visual L2 input.

Outcomes:
- all 3 still non-applied (pixel_change < ~1, legs unchanged) ->
  non-application is ROBUST to sampling (input-combination property);
- any sample applies the chino (pixel_change >= ~1, visual change) ->
  the failure is SAMPLE-DEPENDENT (stochastic engine application).

No production path, no gate bypass: raw worker calls only (forensics).
"""
import base64
import hashlib
import io
import json
import os
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

urls = (REPO / "evaluation" / ".eval_urls").read_text().split()
env_text = (REPO / "evaluation" / ".eval_env").read_text()
token = re.search(r"^VTON_EVAL_ADMIN_TOKEN=(.+)$", env_text, re.M).group(1).strip()

import httpx
from PIL import Image

OUT = REPO / "evaluation" / "results" / "n2_cache_miss"
OUT.mkdir(parents=True, exist_ok=True)

# 1. locate the A+teal L1 render (sha 0f29f3a547fe...)
target = None
for f in sorted((REPO / "evaluation" / "results" / "n2_isolation").glob("*_l1.png")):
    h = hashlib.sha256(f.read_bytes()).hexdigest()
    if h.startswith("0f29f3a547fe"):
        target = f
        break
assert target, "A+teal L1 render not found"
print("L1 source:", target.name, "sha", hashlib.sha256(target.read_bytes()).hexdigest()[:16], flush=True)

l1 = Image.open(target).convert("RGB")

# 2. olive chino garment payload (same image as matrix B1)
olive = (REPO / "evaluation" / "archtest_inputs" / "garment_rt2.jpg")
olive_b64 = "data:image/jpeg;base64," + base64.b64encode(olive.read_bytes()).decode()

headers = {"X-VTON-Admin": token}
RESULTS = {"l1_sha": hashlib.sha256(target.read_bytes()).hexdigest(),
           "l1_size": list(l1.size), "runs": []}

for i, q in enumerate((92, 95, 88)):
    buf = io.BytesIO()
    l1.save(buf, format="JPEG", quality=q)
    new_bytes = buf.getvalue()
    assert hashlib.sha256(new_bytes).hexdigest() != hashlib.sha256(target.read_bytes()).hexdigest()
    person_b64 = "data:image/jpeg;base64," + base64.b64encode(new_bytes).decode()
    t0 = time.time()
    resp = httpx.post(urls[1], headers=headers, timeout=180, json={
        "job_id": f"n2i_cache_miss_olive_q{q}_{int(time.time())}",
        "user_image_base64_or_url": person_b64,
        "garments": [{"product_id": 999901 + q,
                      "slot_type": "lower",
                      "sleeve_length": "none",
                      "image_base64": olive_b64}],
        "gender_mode": "infer_from_image",
        "output_aspect": "9:16",
    })
    elapsed = round(time.time() - t0, 1)
    rec = {"q": q, "http": resp.status_code, "elapsed_s": elapsed}
    if resp.status_code == 200:
        gj = resp.json()
        rec["verify"] = gj.get("verify")
        rec["model_used"] = gj.get("model_used")
        rend = gj.get("rendered_image_data_url", "")
        if rend.startswith("data:"):
            raw = base64.b64decode(rend.split(",", 1)[1])
            rec["rendered_sha"] = hashlib.sha256(raw).hexdigest()
            (OUT / f"olive_q{q}_L2.png").write_bytes(raw)
    else:
        rec["body"] = resp.text[:200]
    RESULTS["runs"].append(rec)
    print(f"q={q} http={resp.status_code} verify={json.dumps(rec.get('verify'))} {elapsed}s", flush=True)

(OUT / "results.json").write_text(json.dumps(RESULTS, indent=1))
print("WROTE", OUT / "results.json", flush=True)
