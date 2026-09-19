"""Prepare the newly generated Phase-3 inputs (2026-09-16). v2.

Deterministic, documented preprocessing of AI-generated runtime inputs so
they match the cohort's framing conventions (persons 896x1200 portrait,
garment flat-lays tight). Background is modeled as a per-channel plane fit
to the border pixels (handles the studio gradient/vignette); the subject
bbox is the mask of |pixel - background| > 22 with row/column density
filtering (kills sparse shadow noise). Originals preserved as *_raw.
"""
from pathlib import Path

import numpy as np
from PIL import Image

D = Path(__file__).resolve().parents[1] / "dyninputs_fresh"


def fit_bg_plane(arr: np.ndarray, band: int = 6):
    H, W, _ = arr.shape
    ys, xs = [], []
    vals = []
    for y in list(range(band)) + list(range(H - band, H)):
        for x in range(0, W, 4):
            ys.append(y); xs.append(x); vals.append(arr[y, x])
    for x in list(range(band)) + list(range(W - band, W)):
        for y in range(0, H, 4):
            ys.append(y); xs.append(x); vals.append(arr[y, x])
    X = np.stack([np.ones_like(xs, float), np.asarray(xs, float) / W,
                  np.asarray(ys, float) / H], axis=1)
    A = np.asarray(vals, float)
    coef, *_ = np.linalg.lstsq(X, A, rcond=None)
    yy, xx = np.mgrid[0:H, 0:W]
    Z = np.stack([np.ones((H, W)), xx / W, yy / H], axis=-1)
    return (Z @ coef).astype(float)


def subject_bbox(arr: np.ndarray, tol: float = 22.0):
    bg = fit_bg_plane(arr)
    diff = np.abs(arr.astype(float) - bg).max(axis=2)
    mask = diff > tol
    H, W = mask.shape
    row_dens = mask.sum(axis=1)
    col_dens = mask.sum(axis=0)
    rows = row_dens > 0.08 * W
    cols = col_dens > 0.08 * H
    rows_idx, cols_idx = np.where(rows)[0], np.where(cols)[0]
    if len(cols_idx) == 0:
        return None
    x0, x1 = int(cols_idx.min()), int(cols_idx.max())
    y0, y1 = int(rows_idx.min()), int(rows_idx.max())
    # tighten to the actual mask inside the coarse box
    sub = mask[y0:y1 + 1, x0:x1 + 1]
    yy2, xx2 = np.where(sub)
    if len(xx2) == 0:
        return None
    return x0 + int(xx2.min()), y0 + int(yy2.min()), x0 + int(xx2.max()), y0 + int(yy2.max())


def prepare_person(src: str, dst: str, w: int = 896, h: int = 1200):
    im = Image.open(src).convert("RGB")
    arr = np.asarray(im)
    bb = subject_bbox(arr)
    if bb is None:
        raise SystemExit(f"no subject found in {src}")
    x0, y0, x1, y1 = bb
    W, H = im.size
    m = int(0.02 * W)
    x0, y0 = max(0, x0 - m), max(0, y0 - int(0.02 * H))
    x1, y1 = min(W, x1 + m), min(H, y1 + int(0.02 * H))
    crop = im.crop((x0, y0, x1, y1))
    cw, ch = crop.size
    scale = w / cw
    new_h = int(ch * scale)
    crop = crop.resize((w, new_h), Image.LANCZOS)
    if new_h >= h:
        canvas = crop.crop((0, (new_h - h) // 2, w, (new_h - h) // 2 + h))
    else:
        bgc = tuple(int(v) for v in fit_bg_plane(arr)[H // 2, W // 2])
        canvas = Image.new("RGB", (w, h), bgc)
        canvas.paste(crop, (0, (h - new_h) // 2))
    canvas.save(dst, quality=92)
    print(f"person {src}: bbox={bb} -> {dst} {canvas.size}")


def prepare_garment(src: str, dst: str, pad_frac: float = 0.03):
    im = Image.open(src).convert("RGB")
    arr = np.asarray(im)
    bb = subject_bbox(arr)
    if bb is None:
        raise SystemExit(f"no subject found in {src}")
    x0, y0, x1, y1 = bb
    W, H = im.size
    mx, my = int(pad_frac * W), int(pad_frac * H)
    x0, y0 = max(0, x0 - mx), max(0, y0 - my)
    x1, y1 = min(W, x1 + mx), min(H, y1 + my)
    im.crop((x0, y0, x1, y1)).save(dst, quality=92)
    print(f"garment {src}: bbox={bb} -> {dst} {im.crop((x0, y0, x1, y1)).size}")


PERSONS = ["person_I.jpg"]
GARMENTS = ["garment_beige_chino.jpg", "garment_black_joggers.jpg",
            "garment_white_longsleeve.jpg", "garment_gray_longsleeve.jpg",
            "garment_crop_top.jpg", "garment_tank.jpg",
            "garment_modest_tunic.jpg", "garment_arabic_tee_2.jpg",
            "garment_rust_longsleeve.jpg"]


def main():
    import shutil
    for name in PERSONS + GARMENTS:
        p, raw = D / name, D / name.replace(".jpg", "_raw.jpg")
        if p.exists() and not raw.exists():
            shutil.copy2(p, raw)
    for name in PERSONS:
        prepare_person(str(D / name.replace(".jpg", "_raw.jpg")), str(D / name))
    for name in GARMENTS:
        prepare_garment(str(D / f"{name[:-4]}_raw.jpg"), str(D / name))


if __name__ == "__main__":
    main()
