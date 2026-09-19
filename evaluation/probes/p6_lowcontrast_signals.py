"""P6 P0-B/P0-D: orthogonal-signal measurement for the low-contrast zone.

For every P0 matrix case, compute candidate verifier signals on the real
(L1, L2) pair; the negative twin (L1, L1) is trivially zero on the
diff-based channels and is recorded as such (by construction).
Signals (generic lower-body region: bottom 55% of frame, center 60%
width — no person/garment-specific geometry, no fixture IDs):

  s1_lower_pxchg   fraction of lower-region pixels with |diff| > 8
  s2_edge          mean |Sobel magnitude diff| (structural)
  s3_texture       1 - Bhattacharyya overlap of gradient-orientation
                   histograms (texture)
  s4_color_cluster k=3 Lab multi-cluster min-distance: garment reference
                   vs L1-lower and vs L2-lower (closer = applied-ness)

NOTE: the DINOv2 (Apache-2.0, eval-only) embedding channel is
ENVIRONMENT-BLOCKED this session: the pinned weights were lost in the
sandbox rebuild (gitignored) and huggingface.co is proxy-blocked
(401). Recorded, not skipped silently.

No signal is adopted into the gate; the output is a measured separation
table for the report.
"""
import base64
import io
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
OUT = REPO / "evaluation" / "results" / "p6_lowcontrast"
FRESH = REPO / "evaluation" / "dyninputs_fresh"

def lower_region(a):
    h, w = a.shape[:2]
    return a[int(h * 0.45):, int(w * 0.20):int(w * 0.80)]

def sobel_edge(g):
    gy, gx = np.gradient(g.astype(np.float64))
    return np.hypot(gx, gy)

def grad_hist(g, bins=12):
    gy, gx = np.gradient(g.astype(np.float64))
    mag = np.hypot(gx, gy)
    ang = (np.arctan2(gy, gx) * 180 / np.pi + 90) % 180
    m = mag > mag.max() * 0.2 if mag.max() > 0 else np.zeros(mag.shape, bool)
    if m.sum() < 50:
        return np.ones(bins) / bins
    h, _ = np.histogram(ang[m], bins=bins, range=(0, 180), density=True)
    return h / (h.sum() + 1e-12)

def bhattacharyya(p, q):
    """Bhattacharyya coefficient in [0,1]; 1 = identical distributions."""
    p, q = p + 1e-9, q + 1e-9
    p, q = p / p.sum(), q / q.sum()
    return float(np.sum(np.sqrt(p * q)))

def rgb_to_lab(a):
    a = a.reshape(-1, 3) / 255.0
    r, g, b = a[:, 0], a[:, 1], a[:, 2]
    r = np.where(r > 0.04045, ((r + 0.055) / 1.055) ** 2.4, r / 12.92)
    g = np.where(g > 0.04045, ((g + 0.055) / 1.055) ** 2.4, g / 12.92)
    b = np.where(b > 0.04045, ((b + 0.055) / 1.055) ** 2.4, b / 12.92)
    xyz = np.stack([r, g, b], 1) @ np.array([
        [0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722],
        [0.0193, 0.1192, 0.9505]]).T
    xyz = xyz / np.clip(xyz[:, 1:2], 1e-9, None)
    xyz = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return 100 * (np.stack([
        xyz[:, 0] * 3.2406 - xyz[:, 1] * 1.5372 - xyz[:, 2] * 0.4986,
        xyz[:, 0] * -0.9689 + xyz[:, 1] * 1.8758 + xyz[:, 2] * 0.0415,
        xyz[:, 0] * 0.0557 + xyz[:, 1] * -0.2040 + xyz[:, 2] * 1.0570,
    ], 1) + np.array([16, 0, 0]))

def kmeans_centroids(lab, k=3, iters=25):
    n = len(lab)
    rng = np.random.default_rng(7)
    cent = lab[rng.choice(n, k, replace=False)].copy()
    for _ in range(iters):
        d = np.linalg.norm(lab[:, None, :] - cent[None, :, :], axis=2)
        asg = d.argmin(1)
        newc = np.stack([lab[asg == i].mean(0) if (asg == i).any() else cent[i] for i in range(k)])
        if np.allclose(newc, cent, atol=1e-3):
            break
        cent = newc
    return cent

def cluster_min_dist(a_rgb, b_rgb):
    ca = kmeans_centroids(rgb_to_lab(a_rgb))
    cb = kmeans_centroids(rgb_to_lab(b_rgb))
    return float(np.min(np.linalg.norm(ca[:, None, :] - cb[None, :, :], axis=2)))

def main():
    results = json.loads((OUT / "results.json").read_text())

    navy_b64 = None
    try:
        from sqlalchemy.orm import sessionmaker
        from backend.app.core.database import engine as app_engine
        from backend.app.models.catalog import Product
        import httpx
        db = sessionmaker(bind=app_engine)()
        prod = db.query(Product).filter(
            Product.title == "Pleated Tapered Virgin Wool Trousers").first()
        url = prod.thumbnail_url
        navy_b64 = (base64.b64decode(url.split(",", 1)[1])
                    if url.startswith("data:") else httpx.get(url, timeout=60).content)
        db.close()
    except Exception as e:  # noqa: BLE001
        print("navy wool ref fetch failed:", repr(e))

    REF = {
        "B": FRESH / "garment_charcoal_trousers.jpg",
        "C": FRESH / "garment_beige_chino.jpg",
        "F": FRESH / "garment_navy_patterned_trousers.jpg",
        "H": FRESH / "garment_navy_skirt.jpg",
    }

    rows = []
    for case in results["cases"]:
        cid = case["id"]
        l1 = np.asarray(Image.open(OUT / f"raw_{cid}_l1.png").convert("RGB"))
        l2 = np.asarray(Image.open(OUT / f"raw_{cid}_l2.png").convert("RGB"))
        l1g = np.asarray(Image.open(OUT / f"raw_{cid}_l1.png").convert("L"))
        l2g = np.asarray(Image.open(OUT / f"raw_{cid}_l2.png").convert("L"))

        ref = None
        if cid in ("A-E", "D", "G"):
            ref = np.asarray(Image.open(io.BytesIO(navy_b64)).convert("RGB")) if navy_b64 else None
        elif cid in REF:
            ref = np.asarray(Image.open(REF[cid]).convert("RGB"))

        bl, tl = lower_region(l1), lower_region(l2)
        bh, th = lower_region(l1g), lower_region(l2g)
        diff = np.abs(bh.astype(np.int16) - th.astype(np.int16))
        row = {
            "case": cid,
            "contrast": case.get("contrast"),
            "engine_applied_by_verify": case.get("l2", {}).get("verify", {}).get("PASS") is True,
            "verify_pixel_change": (case.get("l2", {}).get("verify") or {}).get("metric_pixel_change"),
            "verify_color_shift": (case.get("l2", {}).get("verify") or {}).get("metric_color_shift"),
            "s1_lower_pxchg": float((diff > 8).mean()),
            "s1_lower_maxdiff": float(diff.max()),
            "s2_edge": float(np.abs(sobel_edge(bh) - sobel_edge(th)).mean()),
            "s3_texture": 1.0 - bhattacharyya(grad_hist(bh), grad_hist(th)),
            "negative_twin": {"s1_lower_pxchg": 0.0, "s2_edge": 0.0, "s3_texture": 0.0,
                              "note": "(L1,L1) by construction — must read not-applied"},
        }
        if ref is not None:
            h, w = l1.shape[:2]
            rh = int(h * 0.55)
            ref_r = np.asarray(Image.fromarray(ref).resize((w, max(rh, 8)), Image.BILINEAR))
            row["s4_ref_l1"] = cluster_min_dist(ref_r, bl)
            row["s4_ref_l2"] = cluster_min_dist(ref_r, tl)
            row["s4_l1_minus_l2"] = row["s4_ref_l1"] - row["s4_ref_l2"]  # >0: L2 closer to garment
        rows.append(row)
        print(f"{cid}: applied={row['engine_applied_by_verify']} "
              f"s1={row['s1_lower_pxchg']:.5f}(max {row['s1_lower_maxdiff']:.0f}) "
              f"s2={row['s2_edge']:.3f} s3={row['s3_texture']:.4f} "
              f"s4Δ={row.get('s4_l1_minus_l2', float('nan')):+.2f}")

    (OUT / "signals.json").write_text(json.dumps({
        "note": ("P0-B orthogonal signals on the P0 matrix. negative_twin = (L1,L1) "
                 "by construction. DINOv2 embedding channel ENVIRONMENT-BLOCKED "
                 "(weights lost in sandbox rebuild, huggingface.co proxy-blocked). "
                 "No signal adopted; measured separation table only."),
        "region": "bottom 55% x center 60% width (generic)",
        "rows": rows}, indent=1))
    print("WROTE", OUT / "signals.json")

if __name__ == "__main__":
    main()
