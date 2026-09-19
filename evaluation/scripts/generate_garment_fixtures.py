"""Deterministic, license-free procedural garment fixture generator.

Phase 0.5 (research/vton-phase05-calibration) — produces flat-lay garment
fixtures with EXACT ground-truth metadata (dominant color, pattern geometry,
text string, logo position, silhouette). All geometry is drawn with PIL from
fixed coordinate templates and a fixed seed: fully reproducible, no external
assets, no copyrighted material.

NOTE: These are stylized flat-lays (vector-like), not photographic product
shots. They are intentionally geometrically clean so that color/pattern/
OCR/silhouette metrics have exact ground truth. Photographic garment fixtures
are tracked as a follow-up (see BASELINE_REPORT limitations).
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "garments"

# Fixed seed => reproducible pattern placement
SEED = 20260915

W, H = 800, 1000
BG = (250, 250, 250)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for p in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


# ---- silhouette templates (polygon coords in 800x1000 space) ----
def tee(coords_long=False, slim=False, oversized=False):
    cx = 400
    shoulder = 170
    half_sh = 150 if oversized else (95 if slim else 120)
    sleeve_len = 0 if coords_long else 1
    if coords_long:
        bottom = 820
        sleeve = 620  # long sleeves
    else:
        bottom = 640
        sleeve = 330 if not slim else 310
    if oversized:
        bottom += 60
    body_w = 230 if oversized else (150 if slim else 185)
    return [
        (cx - half_sh, shoulder),            # left shoulder
        (cx - half_sh - 95, shoulder + 40),  # left sleeve out
        (cx - half_sh - 70, shoulder + sleeve),  # sleeve end
        (cx - body_w, shoulder + 150),       # armpit
        (cx - body_w, bottom),               # left hem
        (cx + body_w, bottom),               # right hem
        (cx + body_w, shoulder + 150),       # right armpit
        (cx + half_sh + 70, shoulder + sleeve),  # right sleeve end
        (cx + half_sh + 95, shoulder + 40),  # right sleeve out
        (cx + half_sh, shoulder),            # right shoulder
        (cx + 45, shoulder - 35),            # right neck
        (cx + 25, shoulder - 50),
        (cx - 25, shoulder - 50),
        (cx - 45, shoulder - 35),            # left neck
    ]


def jacket(long=False, oversized=False):
    base = tee(coords_long=long, oversized=oversized)
    # add lapel V + front opening line as separate draws (handled in render)
    return base


def trousers(oversized=False):
    cx = 400
    top_w = 170 if oversized else 150
    return [
        (cx - top_w, 120), (cx + top_w, 120),
        (cx + top_w + 15, 900), (cx + 60, 900),
        (cx, 560), (cx - 60, 900), (cx - top_w - 15, 900),
    ]


def skirt_aline():
    cx = 400
    return [(cx - 110, 200), (cx + 110, 200), (cx + 260, 780), (cx - 260, 780)]


def dress_midi():
    cx = 400
    return [
        (cx - 140, 150), (cx + 140, 150),          # shoulders
        (cx + 175, 320), (cx + 120, 340),          # right sleeve
        (cx + 95, 460), (cx + 130, 760),           # right side flare
        (cx - 130, 760), (cx - 95, 460),           # left side flare
        (cx - 120, 340), (cx - 175, 320),          # left sleeve
    ]


SILS = {"tee": tee, "longtee": lambda **k: tee(coords_long=True), "sweater": lambda **k: tee(**k),
        "jacket": jacket, "trousers": trousers, "skirt": skirt_aline, "dress": dress_midi}


def _fill(draw, poly, color):
    draw.polygon(poly, fill=color)


def _stripes(draw, poly, color, stripe_color, count=9, vertical=True):
    # clip to poly via bbox, draw stripes, mask back
    x0, y0, x1, y1 = ImageDraw.bbox_from_polygon if False else poly_bounds(poly)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)
    layer = Image.new("RGB", (W, H), stripe_color)
    d = ImageDraw.Draw(layer)
    n = max(2, count)
    if vertical:
        for i in range(n):
            x = x0 + (x1 - x0) * (i + 0.5) / n
            d.line([(x, y0), (x, y1)], fill=color, width=14)
    else:
        for i in range(n):
            y = y0 + (y1 - y0) * (i + 0.5) / n
            d.line([(x0, y), (x1, y)], fill=color, width=14)
    base = Image.new("RGB", (W, H), color)
    out = Image.composite(layer, base, mask)
    return out, mask


def poly_bounds(poly):
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def _check(draw, poly, color, line_color, step=48):
    x0, y0, x1, y1 = poly_bounds(poly)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)
    layer = Image.new("RGB", (W, H), color)
    d = ImageDraw.Draw(layer)
    x = x0
    while x < x1:
        d.line([(x, y0), (x, y1)], fill=line_color, width=8); x += step
    y = y0
    while y < y1:
        d.line([(x0, y), (x1, y)], fill=line_color, width=8); y += step
    return Image.composite(layer, Image.new("RGB", (W, H), color), mask), mask


def _floral(draw, poly, color, petal, center_color, seed):
    x0, y0, x1, y1 = poly_bounds(poly)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)
    layer = Image.new("RGB", (W, H), color)
    d = ImageDraw.Draw(layer)
    rng = random.Random(seed)
    for _ in range(26):
        x = rng.uniform(x0 + 30, x1 - 30); y = rng.uniform(y0 + 30, y1 - 30)
        for a in range(5):
            ang = a * 72
            import math
            px = x + 16 * math.cos(math.radians(ang)); py = y + 16 * math.sin(math.radians(ang))
            d.ellipse([px - 8, py - 8, px + 8, py + 8], fill=petal)
        d.ellipse([x - 6, y - 6, x + 6, y + 6], fill=center_color)
    return Image.composite(layer, Image.new("RGB", (W, H), color), mask), mask


def _logo(d, poly, color, logo_color):
    x0, y0, x1, y1 = poly_bounds(poly)
    cx = (x0 + x1) / 2; cy = y0 + 0.38 * (y1 - y0)
    r = 46
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=logo_color, width=7)
    d.polygon([(cx, cy - 28), (cx + 8, cy - 6), (cx + 30, cy - 6), (cx + 12, cy + 8),
               (cx + 18, cy + 30), (cx, cy + 16), (cx - 18, cy + 30), (cx - 12, cy + 8),
               (cx - 30, cy - 6), (cx - 8, cy - 6)], fill=logo_color)


def _text(d, poly, color, text_color, text):
    x0, y0, x1, y1 = poly_bounds(poly)
    cx = (x0 + x1) / 2; cy = y0 + 0.42 * (y1 - y0)
    f = _font(44)
    try:
        bb = d.textbbox((0, 0), text, font=f)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
    except Exception:
        tw, th = 8 * len(text), 44
    d.text((cx - tw / 2, cy - th / 2), text, fill=text_color, font=f)


def _hem_line(d, poly, color, darker):
    x0, y0, x1, y1 = poly_bounds(poly)
    d.line([(x0 + 20, y1 - 14), (x1 - 20, y1 - 14)], fill=darker, width=6)


def _lapels(d, poly, color, darker):
    cx = 400; shoulder = 170
    d.polygon([(cx - 60, shoulder - 20), (cx - 10, shoulder + 150), (cx - 90, shoulder + 170)], fill=darker)
    d.polygon([(cx + 60, shoulder - 20), (cx + 10, shoulder + 150), (cx + 90, shoulder + 170)], fill=darker)
    d.line([(cx, shoulder + 150), (cx, poly_bounds(poly)[3] - 20)], fill=darker, width=5)


def render(spec: dict) -> tuple[Image.Image, dict]:
    """spec: id, name, silhouette, color(hex), pattern, extras..."""
    img = Image.new("RGB", (W, H), BG)
    poly_fn = SILS[spec["silhouette"]]
    poly = poly_fn(**spec.get("sil_kwargs", {}))
    color = hex2rgb(spec["color"])
    d = ImageDraw.Draw(img)

    meta_extra = {}
    if spec.get("pattern") == "stripes":
        img, mask = _stripes(d, poly, color, hex2rgb(spec["stripe_color"]), count=spec.get("stripe_count", 9), vertical=spec.get("stripe_vertical", True))
        img = img.convert("RGB")
        d = ImageDraw.Draw(img)
        meta_extra.update(pattern_type="stripes", stripe_count=spec.get("stripe_count", 9), stripe_vertical=spec.get("stripe_vertical", True), stripe_color=spec["stripe_color"])
        # re-draw border crispness
        d.polygon(poly, outline=darker(color), width=3)
    elif spec.get("pattern") == "check":
        img, mask = _check(d, poly, color, hex2rgb(spec["stripe_color"]), step=spec.get("check_step", 48))
        d = ImageDraw.Draw(img)
        meta_extra.update(pattern_type="check", check_step=spec.get("check_step", 48), stripe_color=spec["stripe_color"])
        d.polygon(poly, outline=darker(color), width=3)
    elif spec.get("pattern") == "floral":
        img, mask = _floral(d, poly, color, hex2rgb(spec["stripe_color"]), hex2rgb(spec.get("flower_center", "#FFFFFF")), SEED)
        d = ImageDraw.Draw(img)
        meta_extra.update(pattern_type="floral")
        d.polygon(poly, outline=darker(color), width=3)
    else:
        _fill(d, poly, color)
        meta_extra.update(pattern_type="plain")

    if spec.get("has_logo"):
        _logo(d, poly, color, hex2rgb(spec.get("logo_color", "#111111")))
        meta_extra.update(has_logo=True)
    if spec.get("has_text"):
        _text(d, poly, color, hex2rgb(spec.get("text_color", "#FFFFFF")), spec["text"])
        meta_extra.update(has_text=True, expected_text=spec["text"])
    if spec.get("hem_line", True):
        _hem_line(d, poly, color, darker(color))
    if spec.get("lapels"):
        _lapels(d, poly, color, darker(color))
    meta_extra.update(dominant_color=spec["color"], silhouette=spec["silhouette"])
    return img, meta_extra


def hex2rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def darker(c: tuple[int, int, int]) -> tuple[int, int, int]:
    return tuple(max(0, int(v * 0.55)) for v in c)  # type: ignore[return-value]


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    specs = [
        # (id, name, sil, kwargs, color, pattern, extra)
        ("g001", "plain white tee", "tee", {}, "#F4F4F2", "plain", {}),
        ("g002", "plain black tee", "tee", {}, "#1B1B1F", "plain", {}),
        ("g003", "plain navy crewneck sweater", "sweater", {}, "#23355C", "plain", {}),
        ("g004", "plain beige crewneck sweater", "sweater", {}, "#D8C9A8", "plain", {}),
        ("g005", "striped shirt blue-white", "tee", {}, "#F4F4F2", "stripes",
         {"stripe_color": "#2E5FA3", "stripe_count": 10, "stripe_vertical": True}),
        ("g006", "check shirt red-white", "tee", {}, "#F4F4F2", "check",
         {"stripe_color": "#B23A3A", "check_step": 52}),
        ("g007", "floral blouse teal", "tee", {}, "#2E8C86", "floral", {"stripe_color": "#F2E9D8", "flower_center": "#E8B84B"}),
        ("g008", "heather tee with circular logo", "tee", {}, "#B9BDC4", "plain", {"has_logo": True, "logo_color": "#222831"}),
        ("g009", "black tee with text print", "tee", {}, "#1B1B1F", "plain", {"has_text": True, "text_color": "#F4F4F2", "text": "STUDIO 2026"}),
        ("g010", "white long-sleeve shirt", "longtee", {}, "#F4F4F2", "plain", {}),
        ("g011", "light blue polo", "tee", {}, "#A8C6E8", "plain", {}),
        ("g012", "black long-sleeve tee (dark pair)", "longtee", {}, "#1B1B1F", "plain", {}),
        ("g013", "cream blouse (light pair)", "tee", {}, "#EFE7D6", "plain", {}),
        ("g014", "oversized gray blazer", "jacket", {"oversized": True}, "#8A8F98", "plain", {"lapels": True}),
        ("g015", "beige short jacket", "jacket", {}, "#CBB492", "plain", {"lapels": True}),
        ("g016", "navy long coat", "jacket", {"long": True}, "#23355C", "plain", {"lapels": True}),
        ("g017", "olive trench coat", "jacket", {"long": True}, "#6B6B3A", "plain", {"lapels": True}),
        ("g018", "slim black tee (slim pair)", "tee", {"slim": True}, "#202024", "plain", {}),
        ("g019", "oversized black knit sweater (bulky)", "sweater", {"oversized": True}, "#202024", "plain", {}),
        ("g020", "navy chinos (similar-color pair)", "trousers", {}, "#23355C", "plain", {}),
        ("g021", "beige casual trousers", "trousers", {}, "#CBB492", "plain", {}),
        ("g022", "black slim pants (dark pair)", "trousers", {}, "#1B1B1F", "plain", {}),
        ("g023", "off-white trousers (light pair)", "trousers", {}, "#EFE9DC", "plain", {}),
        ("g024", "red midi A-line dress", "dress", {}, "#A63A3A", "plain", {}),
    ]
    slot_map = {"tee": ("upper_inner", "tops"), "longtee": ("upper_inner", "tops"), "sweater": ("upper_inner", "tops"),
                "jacket": ("upper_outer", "tops"), "trousers": ("lower", "bottoms"), "skirt": ("lower", "bottoms"),
                "dress": ("dress", "one-pieces")}
    manifest = []
    for gid, name, sil, skw, color, pattern, extra in specs:
        spec = {"id": gid, "name": name, "silhouette": sil, "sil_kwargs": skw, "color": color, "pattern": pattern, **extra}
        img, mextra = render(spec)
        path = OUT_DIR / f"{gid}.jpg"
        img.save(path, "JPEG", quality=92)
        slot, cat = slot_map[sil]
        manifest.append({
            "garment_id": gid, "name": name, "category": cat, "slot": slot,
            "silhouette": sil, "color_hex": color, "pattern_type": mextra.get("pattern_type", "plain"),
            "has_text": bool(spec.get("has_text")), "has_logo": bool(spec.get("has_logo")),
            "expected_text": spec.get("text"), "dominant_color": spec["color"],
            "difficulty": extra.get("difficulty", "medium"),
            "expected_properties": build_expected(spec, mextra),
            "image": f"fixtures/garments/{gid}.jpg",
            "provenance": "procedural (PIL, seed=20260915, deterministic)",
        })
    (OUT_DIR.parent / "garment_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"WROTE {len(manifest)} garments -> {OUT_DIR}")


def build_expected(spec, mextra):
    props = [f"color~{spec['color']}", f"pattern={mextra.get('pattern_type')}"]
    if spec.get("has_logo"):
        props.append("logo=circular-star chest center")
    if spec.get("has_text"):
        props.append(f"text='{spec['text']}'")
    if spec.get("lapels"):
        props.append("lapels=V-front jacket")
    if spec.get("silhouette") == "dress":
        props.append("one-piece dress")
    return props


if __name__ == "__main__":
    main()
