"""Baseline runner: CURRENT FASHN single-garment pipeline, UNMODIFIED (Phase 0.5 §9).

Runs the full job matrix against the EVAL worker deployment (separate Modal app
`confit-vton-worker-segfee-eval`; production deployment untouched). Multi-layer
outfits are chained CLIENT-SIDE (layer-k output = layer-(k+1) person input) —
the same sequential pattern the CONFIT backend already uses; zero production
change.

Evidence discipline:
  - every number recorded here is MEASURED (wall clock, response timings, dims).
  - NO image bytes are logged: only sha256 sidecars + metadata.
  - outputs/ dir is gitignored; manifests carry sha256 for reproducibility.
"""
from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path

import requests
from PIL import Image

EVAL_ROOT = Path(__file__).resolve().parent.parent
RESULTS = EVAL_ROOT / "results"
OUTPUTS = RESULTS / "outputs"

PERSONS = EVAL_ROOT / "fixtures" / "persons"
GARMENTS = EVAL_ROOT / "fixtures" / "garments"


def load_env():
    env = {}
    for line in (EVAL_ROOT / ".eval_env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"')
    return env


def load_urls():
    lines = (EVAL_ROOT / ".eval_urls").read_text().split()
    return {"health": lines[0], "process": lines[1], "readiness": lines[2]}


def data_uri(path: Path, mime: str = "image/jpeg") -> str:
    return f"data:{mime};base64," + base64.b64encode(Path(path).read_bytes()).decode()


def sha256_file(path: Path) -> str:
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_one(process_url: str, token: str, job_id: str, person_uri: str,
            garment: dict, timeout: int = 600) -> dict:
    body = {
        "job_id": job_id,
        "user_image_base64_or_url": person_uri,
        "garments": [{"slot_type": garment["slot"], "image_base64": garment["uri"]}],
    }
    t0 = time.time()
    try:
        r = requests.post(process_url, headers={"X-VTON-Admin": token, "Content-Type": "application/json"},
                          json=body, timeout=timeout)
        wall = time.time() - t0
        try:
            j = r.json()
        except Exception:
            j = {"raw": r.text[:500]}
        # NOTE: image data returned to caller for saving; the PERSISTED record
        # strips it (no image data in logs/records).
        return {"job_id": job_id, "http": r.status_code, "wall_s": round(wall, 2), "response": j}
    except Exception as e:
        return {"job_id": job_id, "http": None, "wall_s": round(time.time() - t0, 2),
                "response": {"error": f"{type(e).__name__}: {str(e)[:200]}"}}


def main():
    env = load_env()
    urls = load_urls()
    token = env["VTON_EVAL_ADMIN_TOKEN"]
    outfits = json.loads((EVAL_ROOT / "fixtures" / "outfits.json").read_text())["outfits"]
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    record_path = RESULTS / "baseline_runs.json"
    record = {
        "run_id": "baseline-20260915",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "deployment": "confit-vton-worker-segfee-eval (separate from production)",
        "engine": "fashn_vton_segfee @ fork 7c0f10af (unmodified)",
        "urls": urls,
        "jobs": [],
    }

    h = requests.get(urls["health"], timeout=60).json()
    record["health_before"] = h

    for outfit in outfits:
        oid = outfit["outfit_id"]
        person_path = PERSONS / f"{outfit['person_id']}.jpg"
        person_uri = data_uri(person_path)
        person_sha = sha256_file(person_path)
        prev_out: Path | None = None
        for layer in outfit["layers"]:
            gid = layer["garment_id"]
            gpath = GARMENTS / f"{gid}.jpg"
            guri = data_uri(gpath)
            gsha = sha256_file(gpath)
            if layer["order"] == 1:
                cur_person_uri = person_uri
                cur_person_sha = person_sha
            else:
                cur_person_uri = data_uri(prev_out)
                cur_person_sha = sha256_file(prev_out)
            job_id = f"{oid.replace('/', '_')}-L{layer['order']}-{gid}".replace(" ", "")
            res = run_one(urls["process"], token, job_id, cur_person_uri,
                          {"slot": layer["slot"], "uri": guri})
            entry = {
                "outfit_id": oid, "arm": outfit["arm"], "person_id": outfit["person_id"],
                "person_sha256": cur_person_sha[:16],
                "order": layer["order"], "garment_id": gid, "slot": layer["slot"],
                "garment_sha256": gsha[:16], "chained_input": layer["order"] > 1,
                "http": res["http"], "wall_s": res["wall_s"],
            }
            if res["http"] == 200:
                rj = dict(res["response"])
                out_b64 = rj.get("rendered_image_data_url")
                rj.pop("rendered_image_data_url", None)
                entry["response_meta"] = rj
                out_path = OUTPUTS / f"{oid}-L{layer['order']}-{gid}.jpg"
                if out_b64:
                    clean = out_b64.split(",", 1)[-1] if out_b64.startswith("data:") else out_b64
                    img = Image.open(__import__("io").BytesIO(base64.b64decode(clean))).convert("RGB")
                    img.save(out_path, "JPEG", quality=95)
                    entry["output_sha256"] = sha256_file(out_path)
                    entry["output_dims"] = [img.size[0], img.size[1]]
                    prev_out = out_path
                entry["worker_timing"] = {k: rj.get(k) for k in
                                          ("execution_time_ms", "total_time_ms", "inference_time_ms") if k in rj}
                entry["worker_model"] = rj.get("model_used")
            record["jobs"].append(entry)
            print(f"[{len(record['jobs'])}] {job_id} http={res['http']} wall={res['wall_s']}s", flush=True)
            if res["http"] != 200:
                print(f"  FAIL: {json.dumps(res['response'])[:300]}", flush=True)
                if layer["order"] > 1:
                    print(f"  -> aborting remaining layers of {oid} (chained input unavailable)", flush=True)
                    break
            if res["http"] == 200 and not entry.get("output_sha256"):
                print(f"  -> no output saved for {job_id}; aborting chain", flush=True)
                if layer["order"] > 1 or any(l["order"] > layer["order"] for l in outfit["layers"]):
                    break
            # save progress
            record_path.write_text(json.dumps(record, indent=1))

    # ---- determinism check: re-run first single garment job, compare sha256
    first = [j for j in record["jobs"] if j["arm"] == "SINGLE" and j["http"] == 200][0]
    det_outfit = next(o for o in outfits if o["outfit_id"] == first["outfit_id"])
    person_uri = data_uri(PERSONS / f"{det_outfit['person_id']}.jpg")
    gid = first["garment_id"]
    guri = data_uri(GARMENTS / f"{gid}.jpg")
    det_job_id = f"{first['outfit_id']}-L1-{gid}-DET2"
    res2 = run_one(urls["process"], token, det_job_id, person_uri, {"slot": first["slot"], "uri": guri})
    det = {"rerun_job_id": det_job_id, "original_job": f"{first['outfit_id']}-L1-{gid}",
           "original_sha256": first.get("output_sha256"), "identical": None}
    if res2["http"] == 200:
        rj = res2["response"]
        out_b64 = rj.get("rendered_image_data_url")
        if out_b64:
            clean = out_b64.split(",", 1)[-1] if out_b64.startswith("data:") else out_b64
            img = Image.open(__import__("io").BytesIO(base64.b64decode(clean))).convert("RGB")
            out_path = OUTPUTS / f"{first['outfit_id']}-L1-{gid}-DET2.jpg"
            img.save(out_path, "JPEG", quality=95)
            det["rerun_sha256"] = sha256_file(out_path)
            det["identical"] = det["rerun_sha256"] == det["original_sha256"]
    record["determinism_check"] = det
    print("DETERMINISM:", json.dumps(det), flush=True)

    h = requests.get(urls["health"], timeout=60).json()
    record["health_after"] = h
    record["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    record_path.write_text(json.dumps(record, indent=1))
    ok = sum(1 for j in record["jobs"] if j["http"] == 200)
    print(f"DONE {ok}/{len(record['jobs'])} ok -> {record_path}", flush=True)


if __name__ == "__main__":
    main()
