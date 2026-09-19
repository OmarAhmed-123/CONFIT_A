"""Person_I framing (Phase-3, 2026-09-16). v4 — lightness-based.

The studio shot (1408x768 landscape) has a radial vignette + a bright floor
reflection that defeat background-plane differencing. The person is the only
dramatically dark, tall, centered object (charcoal shirt + navy joggers).
Strategy: fit a quadratic background from wall-only samples (outer 15% cols +
top 10% rows), diff, then pick the tall narrow connected component whose
centroid is horizontally central. Deterministic; original = person_I_raw.jpg.
"""
import numpy as np
from PIL import Image
from scipy import ndimage

D = "/home/user/CONFIT_A/evaluation/dyninputs_fresh"
im = Image.open(f"{D}/person_I_raw.jpg").convert("RGB")
arr = np.asarray(im).astype(float)
H, W, _ = arr.shape

# --- quadratic background from wall-only samples ---
ys, xs, vals = [], [], []
for x in list(range(0, int(W * 0.15), 3)) + list(range(int(W * 0.85), W, 3)):
    for y in range(0, H, 3):
        ys.append(y); xs.append(x); vals.append(arr[y, x])
for y in list(range(0, int(H * 0.10), 2)):
    for x in range(0, W, 8):
        ys.append(y); xs.append(x); vals.append(arr[y, x])
ux = np.asarray(xs, float) / W
uy = np.asarray(ys, float) / H
Xf = np.stack([np.ones_like(ux), ux, uy, ux * ux, uy * uy, ux * uy], axis=1)
coef, *_ = np.linalg.lstsq(Xf, np.asarray(vals, float), rcond=None)
yy, xx = np.mgrid[0:H, 0:W]
uu, vv = xx / W, yy / H
Zf = np.stack([np.ones((H, W)), uu, vv, uu * uu, vv * vv, uu * vv], axis=-1)
bg = Zf @ coef
diff = np.abs(arr - bg).max(axis=2)
mask = diff > 18

# --- pick the tall, narrow, horizontally-central component ---
lab, n = ndimage.label(mask)
best = None
for i in range(1, n + 1):
    comp = lab == i
    area = int(comp.sum())
    if area < 3000:
        continue
    yy2, xx2 = np.where(comp)
    cw = xx2.max() - xx2.min() + 1
    chh = yy2.max() - yy2.min() + 1
    ar = chh / cw
    cx = xx2.mean() / W
    fill = area / (cw * chh)
    if 1.2 < ar < 6 and 0.2 < cx < 0.8 and fill > 0.2:
        score = abs(cx - 0.5)
        if best is None or score < best[0]:
            best = (score, int(xx2.min()), int(yy2.min()), int(xx2.max()), int(yy2.max()), area)
assert best, "no person-like component found"
_, x0, y0, x1, y1, area = best
print(f"person bbox=({x0},{y0},{x1},{y1}) w={x1-x0} h={y1-y0} ar={round((y1-y0)/(x1-x0),2)} area={area}")

m = int(0.02 * W)
x0, y0 = max(0, x0 - m), max(0, y0 - m)
x1, y1 = min(W, x1 + m), min(H, y1 + m)
crop = im.crop((x0, y0, x1, y1))
w, h = 896, 1200
cw, chh = crop.size
sc = w / cw
new_h = int(chh * sc)
crop = crop.resize((w, new_h), Image.LANCZOS)
if new_h >= h:
    canvas = crop.crop((0, (new_h - h) // 2, w, (new_h - h) // 2 + h))
else:
    canvas = Image.new("RGB", (w, h), (205, 205, 203))
    canvas.paste(crop, (0, (h - new_h) // 2))
canvas.save(f"{D}/person_I.jpg", quality=92)
print("saved person_I.jpg", canvas.size)
