"""OCR text-fidelity metric (Phase 0.5).

Engine: EasyOCR (Apache-2.0 — re-verified at install; see LICENSE_AUDIT.md).
Tesseract was the first candidate but is NOT installable in this sandbox
(no root for system packages) -> EasyOCR fallback (documented decision).

Semantics:
  - expected_text: fixture ground truth (e.g. "STUDIO 2026").
  - When the garment region is PARTIALLY_VISIBLE / OCCLUDED_VERIFIED, exact
    match is NOT required: partial-substring or word-overlap credit applies
    (documented leniency; no pixel-perfect requirement).
  - When expected_text is None and the garment is plain: reports OCR-absence
    sanity (unexpected text is an artifact signal).
"""
from __future__ import annotations

import re
from functools import lru_cache

_readers: dict = {}


def _get_reader(langs=("en",)):
    """One EasyOCR reader per language set (cached).

    Phase 1 §12: English and Arabic are measured SEPARATELY with their own
    reader/models — no cross-language capability assumption. Mixed text uses
    the combined ("en","ar") reader and is reported under its own label.
    """
    key = tuple(sorted(langs))
    if key not in _readers:
        import easyocr
        _readers[key] = easyocr.Reader(list(key), gpu=False, verbose=False)
    return _readers[key]


def read_text(img, box: tuple[int, int, int, int], langs=("en",)) -> list[dict]:
    from PIL import Image
    import io
    crop = img.crop(box) if isinstance(img, Image.Image) else Image.open(img).crop(box)
    buf = io.BytesIO()
    crop.convert("RGB").save(buf, "JPEG", quality=95)
    res = _get_reader(langs).readtext(buf.getvalue())
    out = []
    for item in res:
        # easyocr returns (bbox, text, conf) for bytes inputs and
        # (text, conf, bbox) for PIL — normalize robustly.
        txt = next((x for x in item if isinstance(x, str)), None)
        if txt is None:
            continue
        confs = [x for x in item if isinstance(x, (int, float)) and not isinstance(x, bool)]
        conf = float(confs[0]) if confs else 0.0
        bbox = next((x for x in item if isinstance(x, (list, tuple)) and len(x) == 4), [])
        txt = re.sub(r"\s+", " ", txt).strip()
        if txt:
            out.append({"text": txt, "confidence": round(conf, 3),
                        "bbox": [[int(v) for v in pt] for pt in bbox]})
    return out


def _words(s: str) -> set[str]:
    # Latin + digits + Arabic block (0600-06FF); Arabic letters are not
    # case-folded (no case), kept whole.
    return set(re.findall(r"[a-z0-9\u0600-\u06ff']+", s.lower()))


def text_fidelity(expected_text: str | None, img, box, occluded: bool = False,
                  langs=("en",)) -> dict:
    found = read_text(img, box, langs=langs)
    found_str = " ".join(f["text"] for f in found)
    rep = {"metric": "ocr_text_fidelity", "lang": list(langs),
           "detected": found, "detected_joined": found_str}
    if expected_text is None:
        rep["expected_text"] = None
        rep["unexpected_text_found"] = bool(found_str.strip())
        rep["score"] = (0.0 if found_str.strip() else 1.0)
        rep["note"] = "plain garment: no text expected"
        return rep
    exp_words = _words(expected_text)
    got_words = _words(found_str)
    if occluded:
        # lenient regime: word-overlap credit
        overlap = len(exp_words & got_words) / max(1, len(exp_words))
        exact = expected_text.lower() in found_str.lower()
        rep.update({
            "expected_text": expected_text,
            "exact_match": exact,
            "word_overlap": round(overlap, 3),
            "score": 1.0 if exact else round(overlap, 3),
            "regime": "OCCLUSION_LENIENT (no pixel-perfect requirement)",
        })
    else:
        exact = expected_text.lower() == found_str.lower() or expected_text.lower() in found_str.lower()
        overlap = len(exp_words & got_words) / max(1, len(exp_words))
        rep.update({
            "expected_text": expected_text,
            "exact_match": bool(exact),
            "word_overlap": round(overlap, 3),
            "score": 1.0 if exact else round(0.5 * overlap, 3),
            "regime": "STRICT",
        })
    return rep
