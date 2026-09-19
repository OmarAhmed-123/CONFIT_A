"""Deterministic person-fixture standardization (Phase 0.5 fixture hygiene).

AI-generated person fixtures came out in mixed orientations (some 3:2
landscape, some 4:7 portrait). FASHN renders at the INPUT's aspect ratio
(output_aspect declared-never-applied, D1) — so uncontrolled input aspects
would confound the paired benchmark.

This script normalizes every person fixture to 768x1024 (3:4) via:
  1. background-color bbox detection (corner median),
  2. crop to bbox + 4% margin,
  3. pad to 3:4 with the background color,
  4. resize to 768x1024 (Lanczos).

Fully deterministic; original files preserved as <id>.orig.jpg; the manifest
records the applied transform + bbox for every fixture.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

PERSONS = Path(__file__).resolve().parent.parent / "fixtures" / "persons"
OUT = (768, 1024)


def bg_color(arr: np.ndarray) -> np.ndarray:
    corners = np.concatenate([arr[0, :8], arr[-1, :8], arr[:8, 0], arr[:8, -1]], axis=0)
    return np.median(corners, axis=0)


def standardize(path: Path) -> dict:
    orig = Image.open(path).convert("RGB")
    arr = np.asarray(orig)
    bg = bg_color(arr)
    mask = (np.abs(arr.astype(int) - bg.astype(int)).sum(axis=2) > 45)
    ys, xs = np.where(mask)
    if len(xs) == 0:
        raise RuntimeError(f"no foreground found in {path}")
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    w = x1 - x0
    h = y1 - y0
    mx, my = int(0.04 * w), int(0.04 * h)
    x0 = max(0, x0 - mx); y0 = max(0, y0 - my)
    x1 = min(arr.shape[1], x1 + mx); y1 = min(arr.shape[0], y1 + my)
    crop = orig.crop((x0, y0, x1, y1))
    cw, ch = crop.size
    target_ratio = OUT[0] / OUT[1]
    cur_ratio = cw / ch
    if abs(cur_ratio - target_ratio) < 0.01:
        padded = crop
    elif cur_ratio < target_ratio:  # too narrow -> pad sides
        nw = int(round(ch * target_ratio))
        canvas = Image.new("RGB", (nw, ch), tuple(int(v) for v in bg))
        canvas.paste(crop, ((nw - cw) // 2, 0))
        padded = canvas
    else:  # too wide -> pad top/bottom
        nh = int(round(cw / target_ratio))
        canvas = Image.new("RGB", (cw, nh), tuple(int(v) for v in bg))
        canvas.paste(crop, (0, (nh - ch) // 2))
        padded = canvas
    final = padded.resize(OUT, Image.LANCZOS)
    orig_backup = path.with_suffix(".orig.jpg")
    if not orig_backup.exists():
        orig.save(orig_backup, "JPEG", quality=92)
    final.save(path, "JPEG", quality=92)
    return {
        "original_size": [orig.size[0], orig.size[1]],
        "bbox": [x0, y0, x1, y1],
        "bg_color_hex": "#%02X%02X%02X" % tuple(int(v) for v in bg),
        "final_size": list(OUT),
        "transform": "bg-bbox-crop+4%margin, 3:4 pad (bg color), resize 768x1024 (deterministic)",
    }


def main():
    man_path = PERSONS.parent / "person_manifest.json"
    man = json.loads(man_path.read_text())
    report = {}
    for e in man:
        p = PERSONS / f"{e['person_id']}.jpg"
        r = standardize(p)
        e["standardization"] = r
        report[e["person_id"]] = r
        print(f"{e['person_id']}: {r['original_size']} bbox={r['bbox']} -> {r['final_size']}")
    man_path.write_text(json.dumps(man, indent=2))
    (PERSONS.parent / "standardization_report.json").write_text(json.dumps(report, indent=2))
    print("standardized", len(report), "persons")


if __name__ == "__main__":
    main()
