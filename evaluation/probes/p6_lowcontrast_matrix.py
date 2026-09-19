"""P6 P0: low-contrast N=2 bottom-garment verification matrix.

Primary technical objective of Phase 6: resolve whether the person-I
navy-on-navy ``VTON_LAYER_NOT_APPLIED`` is (a) genuine engine
non-application or (b) a verifier limitation when the requested garment is
visually near-identical to the person's existing lower garment.

Method (P0-A): CALL THE WORKER DIRECTLY (no service gate) so the exact L2
render bytes + verify metrics are captured even when verify.PASS is not
True. Per case:
  1. L1 = worker(person, [teal tee, short sleeve])   -> exact L1 bytes
  2. L2 = worker(L1 bytes, [target bottom])          -> exact L2 bytes + verify
Persisted: hashes + verify metrics + timings only (NO base64 payloads in
JSON — P8 hygiene). Raw PNGs saved as separate files (evaluation synthetic
persons; no user PII).

Cases (contrast classes per Phase-6 prompt §3):
  A-E  same family AND same color, different construction:
       navy joggers (person I input) -> navy wool trousers
  B    moderate: navy joggers -> charcoal wool trousers
  C    clear:    navy joggers -> beige chino
  D    reverse:  cream chinos (person C input) -> navy wool trousers
  F    same color, strong texture: navy joggers -> navy micro-check
  G    different shape: wide light-gray chinos (person K) -> slim navy wool
  H    category change: blue denim (person A) -> navy pleated skirt

Synthetic garments (charcoal, navy micro-check, skirt) are AI-generated
flat-lay product images (synthetic evaluation inputs, labeled as such).
"""
import base64
import hashlib
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

import httpx
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

urls = (REPO / "evaluation" / ".eval_urls").read_text().split()
env_text = (REPO / "evaluation" / ".eval_env").read_text()
token = re.search(r"^VTON_EVAL_ADMIN_TOKEN=(.+)$", env_text, re.M).group(1).strip()
PROCESS_URL = urls[1]
HEADERS = {"X-VTON-Admin": token, "Content-Type": "application/json"}

OUT = REPO / "evaluation" / "results" / "p6_lowcontrast"
OUT.mkdir(parents=True, exist_ok=True)

FRESH = REPO / "evaluation" / "dyninputs_fresh"
ARCH = REPO / "evaluation" / "archtest_inputs"

TOP = ARCH / "garment_rt1.jpg"  # teal tee, short sleeve (sleeve gate N/A)
BOTTOMS = {
    "navy_wool": "https://confit.local/catalog/navy-wool-trousers.jpg",  # replaced by base64 below
    "charcoal": FRESH / "garment_charcoal_trousers.jpg",
    "beige": FRESH / "garment_beige_chino.jpg",
    "navy_pat": FRESH / "garment_navy_patterned_trousers.jpg",
    "navy_skirt": FRESH / "garment_navy_skirt.jpg",
}

CASES = [
    ("A-E", "I", "navy_wool", "same_family_same_color_diff_construction"),
    ("B",   "I", "charcoal",  "moderate_contrast"),
    ("C",   "I", "beige",     "clear_contrast"),
    ("D",   "C", "navy_wool", "reverse_beige_to_navy"),
    ("F",   "I", "navy_pat",  "same_color_strong_texture"),
    ("G",   "K", "navy_wool", "different_shape_wide_to_slim"),
    ("H",   "A", "navy_skirt","category_change_pants_to_skirt"),
]

def data_url_bytes(b: bytes, mime="image/jpeg") -> str:
    return f"data:{mime};base64," + base64.b64encode(b).decode()

def b64(p: Path, mime="image/jpeg") -> str:
    return base64.b64encode(p.read_bytes()).decode()

NAVY_WOOL_B64 = None  # filled from catalog product below (service DB)

def worker_call(job_id: str, person_data_url: str, garment_b64: str, slot: str) -> dict:
    payload = {
        "job_id": job_id,
        "user_image_base64_or_url": person_data_url,
        "garments": [{"product_id": job_id, "slot_type": slot,
                      "sleeve_length": "none" if slot == "lower" else "short",
                      "image_base64": "data:image/jpeg;base64," + garment_b64}],
        "gender_mode": "infer_from_image",
        "output_aspect": "9:16",
    }
    t0 = time.time()
    r = httpx.post(PROCESS_URL, json=payload, headers=HEADERS, timeout=600)
    el = round(time.time() - t0, 1)
    if r.status_code != 200:
        return {"http": r.status_code, "error": r.text[:300], "elapsed_s": el}
    d = r.json()
    rend = d.get("rendered_image_data_url", "")
    raw = base64.b64decode(rend.split(",", 1)[1]) if rend.startswith("data:") else b""
    return {"http": 200, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
            "verify": d.get("verify"), "raw": raw, "elapsed_s": el,
            "model_used": d.get("model_used"), "execution_time_ms": d.get("execution_time_ms")}

def get_navy_wool_b64() -> str:
    """Fetch the navy wool trousers product image from the catalog DB."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from backend.app.core.database import engine as app_engine
    from backend.app.models.catalog import Product
    db = sessionmaker(bind=app_engine)()
    try:
        prod = db.query(Product).filter(
            Product.title == "Pleated Tapered Virgin Wool Trousers").first()
        if not prod:
            raise RuntimeError("navy wool trousers product not found")
        url = prod.thumbnail_url
        if url.startswith("data:"):
            return url.split(",", 1)[1]
        r = httpx.get(url, timeout=60)
        return base64.b64encode(r.content).decode()
    finally:
        db.close()

def main():
    navy_b64 = get_navy_wool_b64()
    RESULTS = {"started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "cases": []}
    top_b64 = b64(TOP)
    top_sha = hashlib.sha256(TOP.read_bytes()).hexdigest()[:8]

    for cid, person_key, bkey, contrast in CASES:
        person_p = FRESH / f"person_{person_key}.jpg"
        person_b = person_p.read_bytes()
        if bkey == "navy_wool":
            bottom_b64, bottom_p = navy_b64, None
            bottom_sha = "navy-wool-catalog"
        else:
            bottom_p = BOTTOMS[bkey]
            bottom_b64 = b64(bottom_p)
            bottom_sha = hashlib.sha256(bottom_p.read_bytes()).hexdigest()[:8]
        rec = {"id": cid, "person": person_key, "bottom": bkey, "contrast": contrast,
               "input_sha8": {"person": hashlib.sha256(person_b).hexdigest()[:8],
                              "top": top_sha, "bottom": bottom_sha},
               "t": time.strftime("%H:%M:%S")}
        # L1: person + teal tee (short sleeve)
        l1 = worker_call(f"p6_{cid}_l1_{uuid.uuid4().hex[:6]}",
                         data_url_bytes(person_b), top_b64, "upper_inner")
        if l1.get("http") != 200:
            rec["l1"] = {"error": l1.get("error"), "http": l1.get("http")}
            RESULTS["cases"].append(rec)
            print(f"{cid}: L1 FAILED {l1.get('error', l1.get('http'))}", flush=True)
            continue
        l1raw = l1.pop("raw")
        (OUT / f"raw_{cid}_l1.png").write_bytes(l1raw)
        rec["l1"] = {k: l1[k] for k in ("sha256", "bytes", "verify", "elapsed_s")}
        # L2: exact L1 bytes + target bottom (direct worker, no service gate)
        l2 = worker_call(f"p6_{cid}_l2_{uuid.uuid4().hex[:6]}",
                         data_url_bytes(l1raw, "image/png"), bottom_b64, "lower")
        if l2.get("http") != 200:
            rec["l2"] = {"error": l2.get("error"), "http": l2.get("http")}
            RESULTS["cases"].append(rec)
            print(f"{cid}: L2 FAILED {l2.get('error', l2.get('http'))}", flush=True)
            continue
        l2raw = l2.pop("raw")
        (OUT / f"raw_{cid}_l2.png").write_bytes(l2raw)
        rec["l2"] = {k: l2[k] for k in ("sha256", "bytes", "verify", "elapsed_s")}
        RESULTS["cases"].append(rec)
        v1 = rec["l1"]["verify"] or {}
        v2 = rec["l2"]["verify"] or {}
        print(f"{cid} ({person_key}/{bkey}) L1px={v1.get('metric_pixel_change')} "
              f"L2 PASS={v2.get('PASS')} px={v2.get('metric_pixel_change')} "
              f"cs={v2.get('metric_color_shift')} {rec['l2']['elapsed_s']}s", flush=True)

    RESULTS["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    (OUT / "results.json").write_text(json.dumps(RESULTS, indent=1, default=str))
    print("WROTE", OUT / "results.json", flush=True)

if __name__ == "__main__":
    main()
