"""Phase 1 §7 — long-sleeve weak-change failure: ROOT CAUSE INVESTIGATION.

Phase 0.5 evidence: 10 worker-verify FAILs (weak change), 2 judge-zero renders
(S_g010 white long-sleeve shirt on p010; S_g012 black long-sleeve tee on p007...
see baseline_runs.json). This script:

1. REPRODUCTION MATRIX: g010/g012 (long-sleeve) x all 10 persons, controls
   g001/g002 x 3 persons.
2. ALTERNATIVE FLAT-LAY GEOMETRIES (hypothesis: procedural long-sleeve
   template is out-of-distribution for the engine):
     g110 — long-sleeve, sleeves laid horizontally (common catalog flat-lay)
     g111 — long-sleeve raglan, sleeves angled 45 deg
   run on the previously failing persons + one known-good person.
3. Per-output QUANTIFICATION: worker verify block, overall delta-E vs input,
   SLEEVE-REGION delta-E (pose-derived upper-arm + forearm boxes) vs garment
   color — i.e. did the engine actually paint sleeves?

Outputs: evaluation/results/rootsleeve_runs.json + outputs/rootsleeve/*.jpg
"""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import numpy as np
import requests
from PIL import Image

EVAL_ROOT = Path(__file__).resolve().parent.parent
RESULTS = EVAL_ROOT / "results"
OUT_DIR = RESULTS / "outputs" / "rootsleeve"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_env():
    env = {}
    for line in (EVAL_ROOT / ".eval_env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"')
    return env


def load_urls():
    parts = (EVAL_ROOT / ".eval_urls").read_text().split()
    return {"process": parts[1]}


def data_uri(path: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(Path(path).read_bytes()).decode()


def sleeve_boxes(img: Image.Image) -> dict:
    """Pose-derived upper-arm/forearm boxes (both arms if visible)."""
    import sys
    sys.path.insert(0, str(EVAL_ROOT))
    from vton_metrics.pose_metrics import pose_landmarks
    res = pose_landmarks(img)
    if res is None:
        return {}
    xy, vis = res
    w, h = img.size
    out = {}
    for side, (sh, el, wr) in {"left": (11, 13, 15), "right": (12, 14, 16)}.items():
        if min(vis[sh], vis[el], vis[wr]) <= 0.4:
            continue
        pts = np.array([xy[sh], xy[el], xy[wr]])
        x0, y0 = pts.min(axis=0); x1, y1 = pts.max(axis=0)
        pad = 0.25 * (x1 - x0 + y1 - y0) / 2
        x0 = max(0, int(x0 - pad)); y0 = max(0, int(y0 - pad))
        x1 = min(w, int(x1 + pad)); y1 = min(h, int(y1 + pad))
        out[side] = (x0, y0, x1, y1)
    return out


def region_delta_e(img: Image.Image, box, hex_color: str) -> float:
    import sys
    sys.path.insert(0, str(EVAL_ROOT))
    from vton_metrics import color_metrics
    return color_metrics.region_color_delta_e(img, box, hex_color)["delta_e_mean"]


def run_one(process_url, token, job_id, person_uri, garment_path, slot):
    body = {"job_id": job_id, "user_image_base64_or_url": person_uri,
            "garments": [{"slot_type": slot, "image_base64": data_uri(garment_path)}]}
    t0 = time.time()
    r = requests.post(process_url, headers={"X-VTON-Admin": token, "Content-Type": "application/json"},
                      json=body, timeout=600)
    wall = time.time() - t0
    try:
        j = r.json()
    except Exception:
        j = {"raw": r.text[:300]}
    return {"http": r.status_code, "wall_s": round(wall, 2), "body": j}


def make_alt_fixtures():
    """Deterministic alternative long-sleeve flat-lays (same generator family)."""
    from PIL import ImageDraw
    W, H = 800, 1000
    bg = (250, 250, 250)
    gdir = EVAL_ROOT / "fixtures" / "garments"

    def save(name, poly, color):
        img = Image.new("RGB", (W, H), bg)
        d = ImageDraw.Draw(img)
        d.polygon(poly, fill=color)
        d.polygon(poly, outline=tuple(max(0, int(c * 0.55)) for c in color), width=3)
        img.save(gdir / name, "JPEG", quality=92)

    # g110: sleeves laid horizontally (classic flat-lay)
    cx, sh = 400, 170
    poly = [
        (cx - 150, sh), (cx - 420, sh + 60), (cx - 420, sh + 150), (cx - 185, sh + 150),
        (cx - 185, 640), (cx + 185, 640), (cx + 185, sh + 150),
        (cx + 420, sh + 150), (cx + 420, sh + 60), (cx + 150, sh),
        (cx + 45, sh - 35), (cx + 25, sh - 50), (cx - 25, sh - 50), (cx - 45, sh - 35),
    ]
    save("g110.jpg", poly, (244, 244, 242))
    # g111: raglan 45-deg sleeves
    poly = [
        (cx - 150, sh), (cx - 330, sh + 260), (cx - 250, sh + 320), (cx - 185, sh + 190),
        (cx - 185, 640), (cx + 185, 640), (cx + 185, sh + 190),
        (cx + 250, sh + 320), (cx + 330, sh + 260), (cx + 150, sh),
        (cx + 45, sh - 35), (cx + 25, sh - 50), (cx - 25, sh - 50), (cx - 45, sh - 35),
    ]
    save("g111.jpg", poly, (27, 27, 31))
    # manifest entries (appended)
    man_path = EVAL_ROOT / "fixtures" / "garment_manifest.json"
    man = json.loads(man_path.read_text())
    for gid, name, color in (("g110", "white long-sleeve shirt, sleeves laid horizontal", "#F4F4F2"),
                             ("g111", "black raglan long-sleeve tee, 45deg sleeves", "#1B1B1F")):
        if not any(g["garment_id"] == gid for g in man):
            man.append({
                "garment_id": gid, "name": name, "category": "tops", "slot": "upper_inner",
                "silhouette": "longtee_alt", "color_hex": color, "pattern_type": "plain",
                "has_text": False, "has_logo": False, "expected_text": None,
                "dominant_color": color, "difficulty": "high",
                "expected_properties": [f"color~{color}", "pattern=plain", "long sleeves (alt geometry)"],
                "image": f"fixtures/garments/{gid}.jpg",
                "provenance": "procedural (PIL, deterministic) — root-cause hypothesis fixture",
            })
    man_path.write_text(json.dumps(man, indent=2))
    print("alt fixtures written: g110 (horizontal sleeves), g111 (raglan 45deg)")


def main():
    make_alt_fixtures()
    env = load_env()
    token = env["VTON_EVAL_ADMIN_TOKEN"]
    urls = load_urls()
    persons = sorted((EVAL_ROOT / "fixtures" / "persons").glob("p*.jpg"))
    gdir = EVAL_ROOT / "fixtures" / "garments"
    rec = {"started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "jobs": []}

    plan = []
    # 1) reproduction: long-sleeve originals x all 10 persons
    for g in ("g010", "g012"):
        for p in persons:
            plan.append((g, p, "repro"))
    # 2) controls x 3 persons
    for g in ("g001", "g002"):
        for p in persons[:3]:
            plan.append((g, p, "control"))
    # 3) alt geometries: on p010/p007 (prev failures) + p001 (known good)
    for g in ("g110", "g111"):
        for pid in ("p010", "p007", "p001"):
            plan.append((g, EVAL_ROOT / "fixtures" / "persons" / f"{pid}.jpg", "alt_geometry"))

    for i, (g, p, kind) in enumerate(plan):
        job_id = f"RS-{g}-{p.stem}-{kind}"
        res = run_one(urls["process"], token, job_id, data_uri(p), gdir / f"{g}.jpg", "upper_inner")
        entry = {"job_id": job_id, "garment": g, "person": p.stem, "kind": kind,
                 "http": res["http"], "wall_s": res["wall_s"]}
        b = res["body"]
        if res["http"] == 200 and isinstance(b, dict) and b.get("rendered_image_data_url"):
            out_b64 = b["rendered_image_data_url"].split(",", 1)[-1]
            out_path = OUT_DIR / f"{job_id}.jpg"
            img = Image.open(__import__("io").BytesIO(base64.b64decode(out_b64))).convert("RGB")
            img.save(out_path, "JPEG", quality=95)
            entry["output"] = str(out_path.relative_to(EVAL_ROOT))
            entry["verify"] = b.get("verify")
            entry["pixel_change"] = b.get("verify", {}).get("metric_pixel_change")
            # sleeve-region analysis: did sleeves get painted?
            gcolor = {"g010": "#F4F4F2", "g012": "#1B1B1F", "g110": "#F4F4F2",
                      "g111": "#1B1B1F", "g001": "#F4F4F2", "g002": "#1B1B1F"}[g]
            boxes = sleeve_boxes(img)
            entry["sleeve_delta_e"] = {side: round(region_delta_e(img, box, gcolor), 2)
                                       for side, box in boxes.items()}
            # arm skin check: median color of forearm box vs typical skin tones
            entry["sleeve_boxes"] = {k: list(v) for k, v in boxes.items()}
        else:
            entry["error"] = str(b)[:200]
        rec["jobs"].append(entry)
        print(f"[{i+1}/{len(plan)}] {job_id} http={res['http']} wall={res['wall_s']}s "
              f"pixel_change={entry.get('pixel_change')} sleeve_de={entry.get('sleeve_delta_e')}", flush=True)
        (RESULTS / "rootsleeve_runs.json").write_text(json.dumps(rec, indent=1))

    rec["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    (RESULTS / "rootsleeve_runs.json").write_text(json.dumps(rec, indent=1))
    weak = [j["job_id"] for j in rec["jobs"] if j.get("pixel_change") is not None and j["pixel_change"] < 1.0]
    print(f"DONE {len(rec['jobs'])} jobs; weak-change (pixel_change<1.0): {len(weak)} -> {weak}")


if __name__ == "__main__":
    main()
