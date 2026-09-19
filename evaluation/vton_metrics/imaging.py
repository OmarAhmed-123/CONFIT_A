"""Image I/O + color-space helpers shared by all Phase 0.5 metrics.

Deterministic, dependency-light (PIL + numpy + scipy for CIEDE2000).
All functions are pure: same inputs -> same outputs.
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = 40_000_000


def load_image(path: str | Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def to_array(img: Image.Image) -> np.ndarray:
    return np.asarray(img, dtype=np.float64)


def image_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def crop_box(img: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    x0, y0, x1, y1 = box
    w, h = img.size
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"empty crop box {box} for image {w}x{h}")
    return img.crop((x0, y0, x1, y1))


def rgb_to_lab(rgb) -> np.ndarray:
    """sRGB [0..1 or 0..255] -> CIELAB (D65). Accepts HxWx3 arrays or Nx3/lists."""
    arr = np.asarray(rgb, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr.reshape(1, 1, -1)
    elif arr.ndim == 2 and arr.shape[-1] == 3:
        arr = arr.reshape(1, 1, 3)
    if arr.max() > 1.0:
        arr = arr / 255.0
    # sRGB -> linear
    linear = np.where(arr <= 0.04045, arr / 12.92, ((arr + 0.055) / 1.055) ** 2.4)
    # linear sRGB -> XYZ (D65)
    M = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = linear @ M.T
    # normalize by D65 white point
    Xn, Yn, Zn = 0.95047, 1.0, 1.08883
    xyz = xyz / np.array([Xn, Yn, Zn])
    eps = 216.0 / 24389.0
    kappa = 24389.0 / 27.0

    def f(t):
        return np.where(t > eps, np.cbrt(t), (kappa * t + 16.0) / 116.0)

    fx, fy, fz = f(xyz[..., 0]), f(xyz[..., 1]), f(xyz[..., 2])
    L = 116.0 * fy - 16.0
    a = 500.0 * (fx - fy)
    b = 200.0 * (fy - fz)
    return np.stack([L, a, b], axis=-1)


def lab_to_rgb_hex_lab(hex_color: str) -> np.ndarray:
    h = hex_color.lstrip("#")
    rgb = np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float64)
    return rgb_to_lab(rgb.reshape(1, 1, 3))[0, 0]


def hex2rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def ciede2000(lab1: np.ndarray, lab2: np.ndarray) -> float:
    """CIEDE2000 between two Lab points (3-vectors). Standard formula (Sharma 2005)."""
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    C1 = np.hypot(a1, b1)
    C2 = np.hypot(a2, b2)
    Cbar = (C1 + C2) / 2.0
    Cbar7 = Cbar ** 7
    G = 0.5 * (1 - np.sqrt(Cbar7 / (Cbar7 + 25.0 ** 7)))
    a1p = (1 + G) * a1
    a2p = (1 + G) * a2
    C1p = np.hypot(a1p, b1)
    C2p = np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360.0
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360.0
    Lbar = (L1 + L2) / 2.0
    Cbarp = (C1p + C2p) / 2.0
    if abs(h1p - h2p) > 180.0:
        h1p += 360.0
    hbarp = (h1p + h2p) / 2.0
    if abs(h1p - h2p) > 180.0:
        hbarp -= 360.0
    if abs(h1p - h2p) * (C1p * C2p) < 1e-9:
        hbarp = h1p + h2p
    T = (1 - 0.17 * np.cos(np.radians(hbarp - 30)) + 0.24 * np.cos(np.radians(2 * hbarp))
         + 0.32 * np.cos(np.radians(3 * hbarp + 6)) - 0.20 * np.cos(np.radians(4 * hbarp - 63)))
    dhp = h2p - h1p
    if abs(dhp) > 180.0:
        dhp -= 360.0 * np.sign(dhp)
    dcp = C1p - C2p
    dhp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dhp) / 2.0)
    dLp = L2 - L1
    dCp = dcp
    SL = 1 + 0.015 * (Lbar - 50) ** 2 / np.sqrt(20 + (Lbar - 50) ** 2)
    Sc = 1 + 0.045 * Cbarp
    Sh = 1 + 0.015 * Cbarp * T
    Cbarp7 = Cbarp ** 7
    Rc = 2 * np.sqrt(Cbarp7 / (Cbarp7 + 25.0 ** 7))
    dtheta = 30 * np.exp(-((hbarp - 275) / 25) ** 2)
    RT = -Rc * np.sin(np.radians(2 * dtheta))
    return float(np.sqrt((dLp / SL) ** 2 + (dCp / Sc) ** 2 + (dhp / Sh) ** 2 + RT * (dCp / Sc) * (dhp / Sh)))


def dominant_color(img: Image.Image, k: int = 3) -> list[dict]:
    """Coarse deterministic dominant colors via uniform LAB quantization (no k-means).

    Returns top-k colors as {'hex', 'lab', 'fraction'}. Deterministic for a given image.
    """
    small = img.resize((64, 64))
    lab = rgb_to_lab(to_array(small)).reshape(-1, 3)
    # quantize to 16 levels per channel
    q = np.round(lab / (90.0 / 15.0) * 1.0).astype(np.int64)  # ~6-unit bins
    idx = q[:, 0] * 300 + q[:, 1] * 300 + q[:, 2]
    vals, counts = np.unique(idx, return_counts=True)
    order = np.argsort(-counts)
    out = []
    n = len(lab)
    for pos in order[:k]:
        v = vals[pos]
        mask = idx == v
        mean_lab = lab[mask].mean(axis=0)
        out.append({
            "hex": _lab_to_hex(mean_lab),
            "lab": [round(float(x), 3) for x in mean_lab],
            "fraction": round(float(counts[order[pos]] / n), 4),
        })
    return out


def _lab_to_hex(lab: np.ndarray) -> str:
    L, a, b = lab
    fy = (L + 16.0) / 116.0
    fx = fy + a / 500.0
    fz = fy - b / 200.0
    eps = 216.0 / 24389.0
    kappa = 24389.0 / 27.0

    def inv(t):
        t3 = t ** 3
        return np.where(t3 > eps, t3, (116.0 * t - 16.0) / kappa)

    X = float(inv(fx)) * 0.95047
    Y = float(inv(fy)) * 1.0
    Z = float(inv(fz)) * 1.08883
    M_inv = np.array([[ 3.2404542, -1.5371385, -0.4985314],
                      [-0.9692660,  1.8760108,  0.0415560],
                      [ 0.0556434, -0.2040259,  1.0572252]])
    linear = np.array([X, Y, Z]) @ M_inv
    linear = np.clip(linear, 0.0, 1.0)
    srgb = np.where(linear <= 0.0031308, 12.92 * linear, 1.055 * linear ** (1 / 2.4) - 0.055)
    rgb = np.clip(np.round(srgb * 255), 0, 255).astype(int)
    return "#%02X%02X%02X" % tuple(rgb)


def histogram(img: Image.Image, bins: int = 16, channels: int = 3) -> np.ndarray:
    small = img.resize((64, 64))
    arr = np.asarray(small, dtype=np.float64)
    hist = np.zeros(bins * channels)
    for c in range(channels):
        h, _ = np.histogram(arr[..., c], bins=bins, range=(0, 255))
        hist[c * bins:(c + 1) * bins] = h
    return hist / hist.sum()


def histogram_intersection(h1: np.ndarray, h2: np.ndarray) -> float:
    return float(np.minimum(h1, h2).sum())


def downscale_to(img: Image.Image, max_dim: int) -> Image.Image:
    w, h = img.size
    if max(w, h) <= max_dim:
        return img
    s = max_dim / max(w, h)
    return img.resize((int(w * s), int(h * s)), Image.BILINEAR)
