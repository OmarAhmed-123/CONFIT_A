"""Feature 07 core — product auto-tagging (FashionCLIP + GLiNER2).

Two honest, complementary models on CPU:

* **FashionCLIP** (patrickjohncyh/fashion-clip, ViT-B/32, MIT license,
  commercial OK): zero-shot classification of the product IMAGE against
  controlled per-axis vocabularies (garment subtype, pattern, occasion,
  material, color). Each axis is an independent softmax; a label becomes a
  tag only when its probability clears the axis threshold. Axes where no
  label clears the threshold are reported ``unresolved`` — never guessed.

* **GLiNER2** (GLiNER v2.1 weights: urchade/gliner_multi-v2.1, 289M,
  Apache-2.0, multilingual → handles Arabic descriptions natively):
  zero-shot NER over the product TITLE + DESCRIPTION, extracting
  {garment, color, material, pattern, occasion, brand} spans with
  confidence scores. Score-gated the same way.

Merge policy (deterministic, provenance-preserving):
  * every emitted tag carries ``{axis, value, confidence, source}``;
  * the same value from both models keeps the higher confidence and both
    sources in ``corroborated_by``;
  * ``product_suggestions`` maps the merged tags onto the platform's real
    product columns (color_family, material, style_tags, occasion_tags)
    — only the fields that earned a confident value are present. Missing
    keys mean "not confident enough", never a default;
  * colors are canonicalised against the catalogue's colour-family
    vocabulary; an unmappable text colour is reported as-is with
    ``unmapped: true`` rather than silently snapped to a nearby name.

Refusal policy: a request with neither image nor text is 422. A request
where BOTH models run but nothing clears threshold is an honest 200 with
``quality: "none"`` and empty suggestions — "we could not tell" is a
valid, reportable answer for a tagging service.
"""
from __future__ import annotations

import io
import re
import time
from typing import Any, Dict, List, Optional

# ───────────────────────── vocabularies (controlled) ────────────────────────

# Fine-grained garment labels (FashionCLIP prompts) → platform category slug.
# The platform has 6 categories; zero-shot works far better on concrete
# garment nouns than on abstract category names, so classify fine and map up.
GARMENT_LABELS: Dict[str, str] = {
    "blazer": "outerwear",
    "trench coat": "outerwear",
    "overcoat": "outerwear",
    "puffer jacket": "outerwear",
    "bomber jacket": "outerwear",
    "leather jacket": "outerwear",
    "knit cardigan": "outerwear",
    "suit jacket": "outerwear",
    "dress shirt": "tops",
    "oxford shirt": "tops",
    "t-shirt": "tops",
    "polo shirt": "tops",
    "sweater": "tops",
    "blouse": "tops",
    "silk top": "tops",
    "knit jumper": "tops",
    "trousers": "bottoms",
    "chinos": "bottoms",
    "jeans": "bottoms",
    "tailored pants": "bottoms",
    "pleated skirt": "bottoms",
    "midi skirt": "bottoms",
    "shorts": "bottoms",
    "evening dress": "dresses",
    "maxi dress": "dresses",
    "slip dress": "dresses",
    "floral dress": "dresses",
    "cocktail dress": "dresses",
    "sneakers": "footwear",
    "leather loafers": "footwear",
    "heels": "footwear",
    "boots": "footwear",
    "sandals": "footwear",
    "leather belt": "accessories",
    "handbag": "accessories",
    "clutch bag": "accessories",
    "scarf": "accessories",
    "sunglasses": "accessories",
    "watch": "accessories",
}

PATTERN_LABELS: List[str] = [
    "solid color garment", "striped garment", "checked plaid garment",
    "floral print garment", "polka dot garment", "animal print garment",
    "geometric print garment", "denim garment", "metallic shimmer garment",
]

# style-tag names for pattern labels (platform style_tags vocabulary)
PATTERN_STYLE_TAGS: Dict[str, str] = {
    "solid color garment": "solid",
    "striped garment": "striped",
    "checked plaid garment": "plaid",
    "floral print garment": "floral",
    "polka dot garment": "polka_dot",
    "animal print garment": "animal_print",
    "geometric print garment": "geometric",
    "denim garment": "denim",
    "metallic shimmer garment": "metallic",
}

OCCASION_LABELS: List[str] = [
    "formal evening wear", "business office outfit", "smart casual outfit",
    "relaxed weekend wear", "sports activewear", "beach resort wear",
    "party outfit", "wedding guest outfit",
]

# occasion labels → platform occasion_tags vocabulary
OCCASION_TAGS: Dict[str, str] = {
    "formal evening wear": "evening",
    "business office outfit": "work",
    "smart casual outfit": "smart_casual",
    "relaxed weekend wear": "casual",
    "sports activewear": "sport",
    "beach resort wear": "beach",
    "party outfit": "party",
    "wedding guest outfit": "wedding",
}

MATERIAL_LABELS: List[str] = [
    "cotton garment", "wool garment", "leather garment", "silk garment",
    "linen garment", "denim garment", "knitted garment", "satin garment",
    "velvet garment", "tweed garment",
]

# zero-shot label → canonical material word for the platform column
MATERIAL_WORDS: Dict[str, str] = {
    "cotton garment": "cotton", "wool garment": "wool", "leather garment": "leather",
    "silk garment": "silk", "linen garment": "linen", "denim garment": "denim",
    "knitted garment": "knit", "satin garment": "satin", "velvet garment": "velvet",
    "tweed garment": "tweed",
}

# Colour families: canonical platform names (aligned with seed catalogue)
# with the synonyms GLiNER text spans are canonicalised against.
COLOR_FAMILIES: Dict[str, List[str]] = {
    "Navy Blue": ["navy", "navy blue", "dark blue", "bleu marine", "كحلي", "أزرق داكن"],
    "Black": ["black", "midnight black", "obsidian black", "jet black", "أسود"],
    "Optic White": ["white", "optic white", "off-white", "cream", "أبيض"],
    "Metallic Gold": ["gold", "metallic gold", "golden", "ذهبي"],
    "Champagne Gold": ["champagne", "champagne gold"],
    "Black & Gold": ["black and gold"],
    "Emerald Green": ["emerald", "emerald green", "green", "olive", "أخضر", "زمردي"],
    "Burgundy": ["burgundy", "maroon", "wine", "بورجوندي"],
    "Grey": ["grey", "gray", "charcoal", "رمادي"],
    "Beige": ["beige", "camel", "tan", "sand", "بيج"],
    "Brown": ["brown", "chocolate", "cognac", "بنبي", "بني"],
    "Red": ["red", "crimson", "أحمر"],
    "Pink": ["pink", "blush", "rose", "وردي"],
    "Blue": ["blue", "sky blue", "light blue", "أزرق"],
    "Yellow": ["yellow", "mustard", "أصفر"],
    "Purple": ["purple", "violet", "lilac", "بنفسجي"],
    "Orange": ["orange", "rust", "برتقالي"],
    "Silver": ["silver", "metallic silver", "فضي"],
}

# FashionCLIP colour prompts are built from the canonical names directly.
COLOR_PROMPT_TEMPLATE = "a product photo of a {} fashion item"

# Per-axis softmax thresholds (tuned on real garment photos 2026-10-03).
AXIS_THRESHOLDS: Dict[str, float] = {
    "category": 0.16,   # 39-way softmax: mass is spread; top label is meaningful
    "pattern": 0.35,
    "occasion": 0.30,
    "material": 0.40,
    "color": 0.30,
}

# GLiNER entity labels → platform axes
GLINER_LABELS = ["garment", "color", "material", "pattern", "occasion", "brand"]
GLINER_SCORE_THRESHOLD = 0.5

MAX_IMAGE_BYTES = 15 * 1024 * 1024
VALID_IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp"}


class TaggingRefused(Exception):
    """Honest refusal with a machine-readable code + actionable message."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ───────────────────────── canonicalisation helpers ─────────────────────────

_ARABIC_RE = re.compile(r"[\u0600-\u06FF]")


def contains_arabic(text: str) -> bool:
    return bool(_ARABIC_RE.search(text or ""))


def canonical_color(text: str) -> Optional[str]:
    """Map a free-text colour span onto a platform colour family.

    Returns None when no family matches — the caller then reports the raw
    span with ``unmapped: true`` instead of snapping to a near name.
    """
    t = (text or "").strip().lower()
    if not t:
        return None
    # longest-synonym-first so "navy blue" beats "blue"
    for family, synonyms in sorted(
        COLOR_FAMILIES.items(), key=lambda kv: -max(len(s) for s in kv[1])
    ):
        for syn in sorted(synonyms, key=len, reverse=True):
            if syn in t:
                return family
    return None


def _normalise_material(text: str) -> str:
    t = (text or "").strip().lower()
    # common text forms → canonical word
    aliases = {
        "cotton": "cotton", "wool": "wool", "woolen": "wool", "woollen": "wool",
        "virgin wool": "wool", "leather": "leather", "genuine leather": "leather",
        "silk": "silk", "linen": "linen", "denim": "denim", "knit": "knit",
        "knitted": "knit", "cashmere": "cashmere", "satin": "satin",
        "velvet": "velvet", "tweed": "tweed", "polyester": "polyester",
        "viscose": "viscose", "المعطف الصوفي": "wool", "قطن": "cotton",
        "صوف": "wool", "جلد": "leather", "حرير": "silk", "كتان": "linen",
    }
    for k, v in sorted(aliases.items(), key=lambda kv: -len(kv[0])):
        if k in t:
            return v
    return t if t else None


def _pattern_to_tag(label: str) -> Optional[str]:
    return PATTERN_STYLE_TAGS.get(label)


def _occasion_to_tag(label: str) -> Optional[str]:
    return OCCASION_TAGS.get(label)


# ───────────────────────── the estimator ────────────────────────────────────

class ProductTagger:
    """Loads both models once; ``tag()`` is stateless and honest."""

    def __init__(self, clip_model=None, gliner_model=None, image_processor=None):
        # Injectable for tests: real models by default, fakes for unit runs
        # that do not need weights (the heavy-path tests load the real ones).
        self._clip = clip_model
        self._clip_processor = image_processor
        self._gliner = gliner_model
        self._loaded = False

    # -- lazy loading ------------------------------------------------------
    def load(self) -> None:
        if self._loaded:
            return
        import torch
        from transformers import CLIPModel, CLIPProcessor

        torch.set_num_threads(2)  # CPU politeness on shared Modal machines
        self._clip = CLIPModel.from_pretrained("patrickjohncyh/fashion-clip")
        self._clip_processor = CLIPProcessor.from_pretrained("patrickjohncyh/fashion-clip")
        self._clip.eval()
        try:
            from gliner import GLiNER

            self._gliner = GLiNER.from_pretrained("urchade/gliner_multi-v2.1")
        except Exception:  # pragma: no cover - surfaced via health
            self._gliner = None
        self._loaded = True

    @property
    def models_loaded(self) -> bool:
        return self._loaded and self._clip is not None

    # -- public API ---------------------------------------------------------
    def tag(
        self,
        image: Optional[bytes] = None,
        title: str = "",
        description: str = "",
        title_ar: str = "",
        description_ar: str = "",
    ) -> Dict[str, Any]:
        started = time.time()
        if image is None and not any([title, description, title_ar, description_ar]):
            raise TaggingRefused(
                "NOTHING_TO_TAG",
                "Provide a product image or a title/description to tag.",
            )

        text_tags: List[Dict[str, Any]] = []
        text_input = "\n".join(x for x in [title, description, title_ar, description_ar] if x)
        if text_input:
            text_tags = self._extract_from_text(text_input)

        image_tags: List[Dict[str, Any]] = []
        if image is not None:
            image_tags = self._classify_image(image)

        merged, unresolved = _merge_tags(image_tags, text_tags)
        suggestions = _product_suggestions(merged)

        sources = set(t["source"] for t in merged)
        if sources == {"fashionclip", "gliner"}:
            quality = "full"
        elif sources == {"fashionclip"}:
            quality = "image_only"
        elif sources == {"gliner"}:
            quality = "text_only"
        else:
            quality = "none"

        return {
            "status": "completed",
            "quality": quality,
            "tags": merged,
            "tag_count": len(merged),
            "axes_unresolved": unresolved,
            "product_suggestions": suggestions,
            "text_language": (
                "ar+en" if (contains_arabic(text_input) and re.search(r"[a-z]", text_input or "", re.I))
                else "ar" if contains_arabic(text_input)
                else "en" if text_input else None
            ),
            "models": {
                "fashionclip": {
                    "id": "patrickjohncyh/fashion-clip",
                    "params": "ViT-B/32",
                    "license": "mit",
                    "commercial": True,
                    "used": bool(image_tags),
                },
                "gliner": {
                    "id": "urchade/gliner_multi-v2.1",
                    "params": "289M (DeBERTa, multilingual)",
                    "license": "apache-2.0",
                    "commercial": True,
                    "used": bool(text_tags),
                },
            },
            "disclaimer": (
                "Auto-tags are model suggestions with per-tag confidence and "
                "provenance. Axes below threshold are reported unresolved, "
                "never guessed. Review before publishing."
            ),
            "timings": {"total_seconds": round(time.time() - started, 3)},
        }

    # -- internals ----------------------------------------------------------
    def _classify_image(self, image_bytes: bytes) -> List[Dict[str, Any]]:
        import torch
        from PIL import Image

        try:
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        except Exception:
            raise TaggingRefused(
                "INVALID_IMAGE", "The image could not be decoded. Use JPEG, PNG or WebP."
            )

        tags: List[Dict[str, Any]] = []
        axes = {
            "category": [f"a product photo of a {l}" for l in GARMENT_LABELS],
            "pattern": [f"a product photo of a {l}" for l in PATTERN_LABELS],
            "occasion": [f"a product photo of {l}" for l in OCCASION_LABELS],
            "material": [f"a product photo of a {l}" for l in MATERIAL_LABELS],
            "color": [COLOR_PROMPT_TEMPLATE.format(f) for f in COLOR_FAMILIES],
        }
        axis_labels = {
            "category": list(GARMENT_LABELS),
            "pattern": PATTERN_LABELS,
            "occasion": OCCASION_LABELS,
            "material": MATERIAL_LABELS,
            "color": list(COLOR_FAMILIES),
        }
        with torch.inference_mode():
            for axis, prompts in axes.items():
                inputs = self._clip_processor(
                    text=prompts, images=img, return_tensors="pt", padding=True
                )
                out = self._clip(**inputs)
                probs = out.logits_per_image.softmax(dim=-1)[0].tolist()
                ranked = sorted(
                    zip(axis_labels[axis], probs), key=lambda kv: kv[1], reverse=True
                )
                thr = AXIS_THRESHOLDS[axis]
                if axis == "category":
                    # keep top-3 above threshold (multi-tagging is useful)
                    kept = [(l, p) for l, p in ranked[:3] if p >= thr]
                else:
                    kept = [(l, p) for l, p in ranked[:2] if p >= thr]
                for label, p in kept:
                    tags.append({
                        "axis": axis,
                        "value": label,
                        "confidence": round(p, 4),
                        "source": "fashionclip",
                    })
        return tags

    def _extract_from_text(self, text: str) -> List[Dict[str, Any]]:
        if self._gliner is None:
            return []
        entities = self._gliner.predict_entities(
            text, GLINER_LABELS, threshold=GLINER_SCORE_THRESHOLD
        )
        tags: List[Dict[str, Any]] = []
        for e in entities:
            value = (e.get("text") or "").strip()
            label = (e.get("label") or "").strip().lower()
            score = float(e.get("score") or 0.0)
            if not value or label not in GLINER_LABELS:
                continue
            tags.append({
                "axis": label if label != "garment" else "category",
                "value": value,
                "confidence": round(score, 4),
                "source": "gliner",
                "language": "ar" if contains_arabic(value) else "en",
            })
        return tags


# ───────────────────────── merge + mapping (pure) ──────────────────────────

def _norm(v: str) -> str:
    return re.sub(r"\s+", " ", (v or "").strip().lower())


def _merge_tags(
    image_tags: List[Dict[str, Any]], text_tags: List[Dict[str, Any]]
) -> tuple:
    """Deterministic merge with provenance. Within an axis:
    * image tags and text tags are different VALUE SPACES (labels vs free
      text) — they are merged as independent tags, not deduped away;
    * exact normalised duplicates (same axis+value) keep the higher
      confidence and record both sources.
    Axes with NO tag above threshold from any source are reported
    unresolved with a reason.
    """
    by_key: Dict[tuple, Dict[str, Any]] = {}
    order: List[tuple] = []
    for t in image_tags + text_tags:
        key = (t["axis"], _norm(t["value"]))
        if key not in by_key:
            by_key[key] = dict(t)
            by_key[key]["corroborated_by"] = [t["source"]]
            order.append(key)
        else:
            existing = by_key[key]
            if t["confidence"] > existing["confidence"]:
                existing["confidence"] = t["confidence"]
            if t["source"] not in existing["corroborated_by"]:
                existing["corroborated_by"].append(t["source"])

    merged = [by_key[k] for k in order]

    seen_axes = {t["axis"] for t in merged}
    unresolved = []
    for axis in ("category", "color", "material", "pattern", "occasion"):
        if axis in seen_axes:
            continue
        reasons = []
        if not image_tags:
            reasons.append("no_image")
        elif not any(t["axis"] == axis for t in image_tags):
            reasons.append("image_below_threshold")
        if not text_tags:
            reasons.append("no_text")
        elif not any(t["axis"] == axis for t in text_tags):
            reasons.append("text_below_threshold")
        unresolved.append({"axis": axis, "reason": "+".join(reasons)})
    return merged, unresolved


def _product_suggestions(merged: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Map merged tags → platform product columns. Only fields with a
    confident value appear; absence means 'not confident', never default."""
    out: Dict[str, Any] = {}

    # color_family: text colour (explicit marketing copy) wins over the
    # pixel guess — per the documented merge policy — with image colour as
    # fallback. Both go through canonicalisation; unmapped → reported as-is.
    text_colors = [t for t in merged if t["axis"] == "color" and t["source"] == "gliner"]
    image_colors = [t for t in merged if t["axis"] == "color" and t["source"] == "fashionclip"]
    best_color, best_color_conf = None, -1.0
    for t in text_colors:
        family = canonical_color(t["value"])
        if family is not None and t["confidence"] > best_color_conf:
            best_color, best_color_conf = family, t["confidence"]
    if best_color is None:
        for t in image_colors:
            family = canonical_color(t["value"])
            if family is not None and t["confidence"] > best_color_conf:
                best_color, best_color_conf = family, t["confidence"]
    if best_color:
        out["color_family"] = best_color
    else:
        # an explicit colour was found but maps to no family — report the
        # raw span, never snap it to a near name
        fallback = (text_colors or image_colors or [None])[0]
        if fallback is not None:
            out["color_family"] = fallback["value"]
            out["color_family_unmapped"] = True

    # material: text material (explicit) preferred, else image guess
    text_mat = [t for t in merged if t["axis"] == "material" and t["source"] == "gliner"]
    img_mat = [t for t in merged if t["axis"] == "material" and t["source"] == "fashionclip"]
    if text_mat:
        out["material"] = _normalise_material(
            max(text_mat, key=lambda t: t["confidence"])["value"]
        )
    elif img_mat:
        best = max(img_mat, key=lambda t: t["confidence"])
        out["material"] = MATERIAL_WORDS.get(best["value"], best["value"])

    # style_tags: garment subtypes (both sources) + pattern tags (image)
    style: List[str] = []
    for t in merged:
        if t["axis"] == "pattern":
            tag = _pattern_to_tag(t["value"])
            if tag and tag not in style:
                style.append(tag)
        elif t["axis"] == "category":
            v = _norm(t["value"])
            if v in GARMENT_LABELS and v not in style:
                style.append(v)
    if style:
        out["style_tags"] = style

    # occasion_tags: image axis + text entities
    occ: List[str] = []
    for t in merged:
        if t["axis"] != "occasion":
            continue
        tag = _occasion_to_tag(t["value"]) if t["source"] == "fashionclip" else _norm(t["value"])
        if tag and tag not in occ:
            occ.append(tag)
    if occ:
        out["occasion_tags"] = occ

    # garment → platform category mapping (suggestion, brand confirms)
    cat = [t for t in merged if t["axis"] == "category" and t["source"] == "fashionclip"]
    if cat:
        best = max(cat, key=lambda t: t["confidence"])
        platform_cat = GARMENT_LABELS.get(_norm(best["value"]))
        if platform_cat:
            out["platform_category"] = platform_cat

    return out
