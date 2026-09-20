"""Deterministic known-bad construction (Phase 0.5 §20 — mandatory).

Corrupts known-good baseline outputs with CONTROLLED, documented defects so
each metric's ability to flag them can be measured (FNR/FPR calibration):

  KB-01 wrong_garment      — splice a different garment's region into the output
  KB-02 missing_garment    — fill garment region with person's base-clothing color
  KB-03 shifted_garment    — translate garment-region content by (dx, dy)
  KB-04 altered_face       — paste face crop of a DIFFERENT fixture person
  KB-05 wrong_color        — LAB hue/lightness shift of garment region
  KB-06 lost_text          — erase the text band of g009 output
  KB-07 layer_swap         — (chained N=2) paste inner garment over outer region
  KB-08 phantom_garment    — paste garment fixture onto head/background region
  KB-09 partial_drop       — (chained N=2) erase 50% of outer-layer region
  KB-10 distorted_pose     — 8° rotation of torso+head region onto own background

All composites are deterministic (fixed offsets/parameters), no randomness.
Each output: results/known_bad/<id>.jpg + sidecar label JSON.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

EVAL_ROOT = Path(__file__).resolve().parent.parent
RESULTS = EVAL_ROOT / "results"
OUTPUTS = RESULTS / "outputs"
KB_DIR = RESULTS / "known_bad"

FIXTURE_PERSON = "p002"   # donor for face swap
SWAP_GARMENT = "g005"     # striped shirt as "wrong garment" donor


def _save(img: Image.Image, kb_id: str, label: str, description: str, source: str):
    KB_DIR.mkdir(parents=True, exist_ok=True)
    p = KB_DIR / f"{kb_id}.jpg"
    img.convert("RGB").save(p, "JPEG", quality=95)
    import hashlib
    (KB_DIR / f"{kb_id}.json").write_text(json.dumps(
        {"kb_id": kb_id, "label": label, "description": description, "source_output": source,
         "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}, indent=1))
    print(f"  wrote {kb_id} ({label})")
    return p


def _garment_box(img: Image.Image, slot: str):
    import sys
    sys.path.insert(0, str(EVAL_ROOT))
    from vton_metrics import regions
    r, st = regions.regions_from_pose(img, slot)
    return r["primary"] if st == "OK" else None


def _face_box(img: Image.Image):
    import sys
    sys.path.insert(0, str(EVAL_ROOT))
    from vton_metrics import regions
    r, st = regions.face_region(img)
    return r["primary"] if st == "OK" else None


def build(run_id: str = "baseline-20260915") -> list[str]:
    rec = json.loads((RESULTS / "baseline_runs.json").read_text())
    jobs = {f"{j['outfit_id']}/L{j['order']}-{j['garment_id']}": j for j in rec["jobs"] if j.get("http") == 200}
    made = []

    def pick(prefix_arm, garment=None, n=1):
        cands = [k for k, j in jobs.items() if j["arm"] == prefix_arm
                 and (garment is None or j["garment_id"] == garment)]
        return cands[:n]

    # ---- KB-01 wrong garment on a white-tee output
    for k in pick("SINGLE", "g001"):
        j = jobs[k]; out = Image.open(OUTPUTS / f"{j['outfit_id']}-L{j['order']}-{j['garment_id']}.jpg").convert("RGB")
        box = _garment_box(out, j["slot"])
        if box:
            donor = Image.open(EVAL_ROOT / "fixtures" / "garments" / f"{SWAP_GARMENT}.jpg").convert("RGB")
            dbox = _tight(donor)
            patch = donor.crop(dbox).resize((box[2] - box[0], box[3] - box[1]))
            out.paste(patch, (box[0], box[1]))
            _save(out, "KB01_wrong_garment", "wrong_garment",
                  f"spliced {SWAP_GARMENT} region over {j['garment_id']} region", k)
            made.append("KB01_wrong_garment")
            break
    # ---- KB-02 missing garment
    for k in pick("SINGLE", "g002"):
        j = jobs[k]; out = Image.open(OUTPUTS / f"{j['outfit_id']}-L{j['order']}-{j['garment_id']}.jpg").convert("RGB")
        box = _garment_box(out, j["slot"])
        if box:
            base = _median_color(out, box)
            for dy in range(box[1], box[3], 4):
                for dx in range(box[0], box[2], 4):
                    out.putpixel((dx, dy), base)
            _save(out, "KB02_missing_garment", "missing_garment",
                  f"filled {j['garment_id']} region with background color", k)
            made.append("KB02_missing_garment")
            break
    # ---- KB-03 shifted garment
    for k in pick("SINGLE", "g003"):
        j = jobs[k]; out = Image.open(OUTPUTS / f"{j['outfit_id']}-L{j['order']}-{j['garment_id']}.jpg").convert("RGB")
        box = _garment_box(out, j["slot"])
        if box:
            dx, dy = 24, 18
            w, h = out.size
            src = out.crop(box)
            out.paste(src, (box[0] + dx, box[1] + dy))
            # refill original box area with surrounding bg
            fill_box = (box[0], box[1], box[0] + dx, box[1] + dy)
            for y in range(*fill_box[1::2]):
                for x in range(fill_box[0], fill_box[2]):
                    if 0 <= y < h:
                        out.putpixel((x, y), out.getpixel((min(w - 1, box[0] - 3), min(h - 1, box[1] - 3))))
            _save(out, "KB03_shifted_garment", "shifted_garment",
                  f"translated garment content by ({dx},{dy})", k)
            made.append("KB03_shifted_garment")
            break
    # ---- KB-04 altered face
    for k in pick("SINGLE", "g004"):
        j = jobs[k]; out = Image.open(OUTPUTS / f"{j['outfit_id']}-L{j['order']}-{j['garment_id']}.jpg").convert("RGB")
        fbox = _face_box(out)
        if fbox:
            donor = Image.open(EVAL_ROOT / "fixtures" / "persons" / f"{FIXTURE_PERSON}.jpg").convert("RGB")
            dfbox = _face_box(donor)
            if dfbox:
                patch = donor.crop(dfbox).resize((fbox[2] - fbox[0], fbox[3] - fbox[1]))
                out.paste(patch, (fbox[0], fbox[1]))
                _save(out, "KB04_altered_face", "altered_face",
                      f"pasted face of fixture {FIXTURE_PERSON} over person {j['person_id']}", k)
                made.append("KB04_altered_face")
                break
    # ---- KB-05 wrong color (hue shift on garment region)
    for k in pick("SINGLE", "g011"):
        j = jobs[k]; out = Image.open(OUTPUTS / f"{j['outfit_id']}-L{j['order']}-{j['garment_id']}.jpg").convert("RGB")
        box = _garment_box(out, j["slot"])
        if box:
            from vton_metrics.imaging import rgb_to_lab  # noqa
            sys_path_fix_import()
            arr = np.asarray(out).astype(np.float64)
            lab = _rgb_lab(arr)
            lab[:, :, 1] += 45.0   # strong a* (red-green) shift
            out2 = Image.fromarray(_lab_rgb(np.clip(lab, 0, 255 if False else None).astype(np.uint8)))
            # paste back region only
            out.paste(out2.crop(box), (box[0], box[1]))
            _save(out, "KB05_wrong_color", "wrong_color",
                  f"LAB a*+45 hue shift on {j['garment_id']} region", k)
            made.append("KB05_wrong_color")
            break
    # ---- KB-06 lost text
    for k in pick("SINGLE", "g009"):
        j = jobs[k]; out = Image.open(OUTPUTS / f"{j['outfit_id']}-L{j['order']}-{j['garment_id']}.jpg").convert("RGB")
        box = _garment_box(out, j["slot"])
        if box:
            # text band = middle 12% height of garment region
            y0 = box[1] + int(0.40 * (box[3] - box[1]))
            y1 = box[1] + int(0.55 * (box[3] - box[1]))
            for y in range(y0, y1):
                for x in range(box[0], box[2]):
                    out.putpixel((x, y), (27, 27, 31))  # garment base black
            _save(out, "KB06_lost_text", "lost_text", "erased text band of g009", k)
            made.append("KB06_lost_text")
            break
    # ---- KB-07 layer swap (chained IO: inner over outer)
    for k in pick("N2_IO", "g017"):
        j = jobs[k]; out = Image.open(OUTPUTS / f"{j['outfit_id']}-L{j['order']}-{j['garment_id']}.jpg").convert("RGB")
        box = _garment_box(out, "upper_outer")
        if box:
            donor = Image.open(EVAL_ROOT / "fixtures" / "garments" / "g010.jpg").convert("RGB")
            dbox = _tight(donor)
            patch = donor.crop(dbox).resize((box[2] - box[0], box[3] - box[1]))
            out.paste(patch, (box[0], box[1]))
            _save(out, "KB07_layer_swap", "layer_swap",
                  "inner garment pasted over outer (trench) region", k)
            made.append("KB07_layer_swap")
            break
    # ---- KB-08 phantom garment
    for k in pick("SINGLE", "g001"):
        j = jobs[k]; out = Image.open(OUTPUTS / f"{j['outfit_id']}-L{j['order']}-{j['garment_id']}.jpg").convert("RGB")
        w, h = out.size
        donor = Image.open(EVAL_ROOT / "fixtures" / "garments" / "g024.jpg").convert("RGB")  # red dress
        dbox = _tight(donor)
        patch = donor.crop(dbox).resize((w // 3, w // 3 * (dbox[3] - dbox[1]) // max(1, (dbox[2] - dbox[0]))))
        out.paste(patch, (w // 4, 5))
        _save(out, "KB08_phantom_garment", "phantom_garment",
              "red dress fixture pasted onto head/background (phantom layer)", k)
        made.append("KB08_phantom_garment")
        break
    # ---- KB-09 partial drop (chained IO: erase 50% of outer region)
    for k in pick("N2_IO", "g015"):
        j = jobs[k]; out = Image.open(OUTPUTS / f"{j['outfit_id']}-L{j['order']}-{j['garment_id']}.jpg").convert("RGB")
        box = _garment_box(out, "upper_outer")
        if box:
            base = _median_color(out, box)
            half = (box[0] + box[2]) // 2
            for y in range(box[1], box[3]):
                for x in range(half, box[2], 2):
                    out.putpixel((x, y), base)
            _save(out, "KB09_partial_drop", "partial_drop",
                  "erased right 50% of outer jacket region", k)
            made.append("KB09_partial_drop")
            break
    # ---- KB-10 distorted pose (rotate upper body 8 deg)
    for k in pick("SINGLE", "g006"):
        j = jobs[k]; out = Image.open(OUTPUTS / f"{j['outfit_id']}-L{j['order']}-{j['garment_id']}.jpg").convert("RGB")
        box = _garment_box(out, j["slot"])
        if box:
            w, h = out.size
            rot_box = (max(0, box[0] - 30), max(0, box[1] - 30), min(w, box[2] + 30), min(h, box[3] + 30))
            crop = out.crop(rot_box).rotate(8, resample=Image.BICUBIC, fillcolor=_median_color(out, rot_box))
            out.paste(crop, (rot_box[0], rot_box[1]))
            _save(out, "KB10_distorted_pose", "distorted_pose",
                  "8° rotation of garment+torso region (approximate pose defect)", k)
            made.append("KB10_distorted_pose")
            break


    # ---- KB11 lost logo (g008 output: erase chest logo region)
    for k in pick("SINGLE", "g008"):
        j = jobs[k]; out = Image.open(OUTPUTS / f"{j['outfit_id']}-L{j['order']}-{j['garment_id']}.jpg").convert("RGB")
        box = _garment_box(out, j["slot"])
        if box:
            # logo sits at chest center of the garment region (fixture: 0.38 of body height, centered)
            cx = (box[0] + box[2]) // 2
            cy = box[1] + int(0.30 * (box[3] - box[1]))
            r = (box[2] - box[0]) // 6
            base = _median_color(out, box)
            for y in range(cy - r, cy + r):
                for x in range(cx - r, cx + r):
                    if 0 <= y < out.size[1] and 0 <= x < out.size[0]:
                        out.putpixel((x, y), base)
            _save(out, "KB11_lost_logo", "lost_logo", "erased chest logo region of g008", k)
            made.append("KB11_lost_logo")
            break
    # ---- KB12 deformed face (affine warp of the face region)
    for k in pick("SINGLE", "g007"):
        j = jobs[k]; out = Image.open(OUTPUTS / f"{j['outfit_id']}-L{j['order']}-{j['garment_id']}.jpg").convert("RGB")
        fbox = _face_box(out)
        if fbox:
            face = out.crop(fbox)
            w, h = face.size
            # strong vertical squash + horizontal skew (deterministic deformation)
            warped = face.transform((w, h), Image.AFFINE, (1.0, 0.35, 0, 0.55, 0.6, 0),
                                    resample=Image.BICUBIC, fillcolor=_median_color(face, (0, 0, w, h)))
            out.paste(warped, (fbox[0], fbox[1]))
            _save(out, "KB12_deformed_face", "deformed_face",
                  "affine warp (0.55x vertical squash + skew) of face region", k)
            made.append("KB12_deformed_face")
            break
    # ---- KB13 duplicated garment (ghost copy of garment region pasted at offset)
    for k in pick("SINGLE", "g002"):
        j = jobs[k]; out = Image.open(OUTPUTS / f"{j['outfit_id']}-L{j['order']}-{j['garment_id']}.jpg").convert("RGB")
        box = _garment_box(out, j["slot"])
        if box:
            w, h = out.size
            dx, dy = 40, 12
            patch = out.crop(box)
            px, py = box[0] + dx, box[1] + dy
            out.paste(patch, (px, py))
            _save(out, "KB13_duplicated_garment", "duplicated_garment",
                  f"ghost duplicate of garment region pasted at offset ({dx},{dy})", k)
            made.append("KB13_duplicated_garment")
            break

    (KB_DIR / "manifest.json").write_text(json.dumps(
        {"constructed_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%S%z"), "n": len(made),
         "known_bad_ids": made}, indent=1))
    print(f"KNOWN BAD DONE: {len(made)} -> {KB_DIR}")
    return made


def sys_path_fix_import():
    import sys
    sys.path.insert(0, str(EVAL_ROOT))


def _tight(img: Image.Image):
    arr = np.asarray(img.convert("RGB"))
    bg = arr[0, 0]
    mask = (np.abs(arr.astype(int) - bg.astype(int)).sum(axis=2) > 30)
    ys, xs = np.where(mask)
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def _median_color(img: Image.Image, box) -> tuple[int, int, int]:
    import statistics
    arr = np.asarray(img.crop(box).resize((16, 16))).reshape(-1, 3)
    return tuple(int(v) for v in np.median(arr, axis=0))


def _rgb_lab(arr: np.ndarray):
    sys_path_fix_import()
    from vton_metrics.imaging import rgb_to_lab
    return rgb_to_lab(arr)


def _lab_rgb(lab: np.ndarray):
    # inverse of imaging.rgb_to_lab (D65)
    from scipy.linalg import inv
    L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    fy = (L + 16.0) / 116.0
    fx = fy + a / 500.0
    fz = fy - b / 200.0
    eps = 216.0 / 24389.0
    kappa = 24389.0 / 27.0

    def inv_f(t):
        t3 = t ** 3
        return np.where(t3 > eps, t3, (116.0 * t - 16.0) / kappa)

    X = inv_f(fx) * 0.95047
    Y = inv_f(fy) * 1.0
    Z = inv_f(fz) * 1.08883
    M_inv = np.array([[3.2404542, -1.5371385, -0.4985314],
                      [-0.9692660, 1.8760108, 0.0415560],
                      [0.0556434, -0.2040259, 1.0572252]])
    linear = np.stack([X, Y, Z], axis=-1) @ M_inv.T
    linear = np.clip(linear, 0.0, 1.0)
    srgb = np.where(linear <= 0.0031308, 12.92 * linear, 1.055 * linear ** (1 / 2.4) - 0.055)
    return np.clip(np.round(srgb * 255), 0, 255).astype(np.uint8)


if __name__ == "__main__":
    import sys
    run_id = sys.argv[1] if len(sys.argv) > 1 else "baseline-20260915"
    build(run_id)
