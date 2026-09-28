"""The one place a try-on instruction is written.

WHY A MODULE AND NOT A STRING AT THE CALL SITE
-----------------------------------------------
`hf_space_client` was passing `garment_description=product.title` straight
through. A raw catalogue title ("Tailored Italian Wool Double-Breasted
Blazer — AW26") carries marketing words, a season code and sometimes the
brand, none of which describe the garment to a diffusion model, and some of
which actively mislead it. Building the text here means every engine — and
any engine added later — asks for the same thing in the same words.

WHAT A PROMPT CAN AND CANNOT DO (stated, because it was asked)
--------------------------------------------------------------
The request was for a fixed prompt that guarantees no change to face or
body. **No prompt can guarantee that**, and saying otherwise would be a
false claim about the technology:

  - IDM-VTON, CatVTON and Leffa are NOT prompt-driven for identity. They
    preserve the person by MASKING: the model only repaints the garment
    region, so the face is literally never resampled. `garment_des` is a
    hint about the CLOTHES; writing "do not change the face" into it does
    nothing, because that text never reaches a component that controls the
    face. Identity holds there because of the mask, not the words.
  - General image models (Gemini, FLUX) DO follow instructions about
    identity, and for those the wording genuinely matters — which is why
    `identity_directive()` exists and is applied only to that family.

So this module produces two different things and is explicit about which
engine gets which. Pretending one prompt covers both would produce confident
text that changes nothing on three of the four engines.

NEUTRALITY
----------
The wording never states the wearer's gender, body size or skin tone. The
person image already carries all of that, and asserting it in words is how
these pipelines end up "correcting" a body toward whatever the phrasing
implies. The same builder therefore serves menswear and womenswear with no
branching.
"""
from __future__ import annotations

import re
from typing import Optional

from backend.app.providers.vton.registry import GarmentCategory

#: Marketing and merchandising noise that describes the LISTING, not the
#: garment. Stripped so the model is not asked to render a season code.
_NOISE = re.compile(
    r"\b("
    r"new\s+in|new|newin|exclusive|limited|edition|essential|signature|iconic|premium|"
    r"luxury|classic|timeless|must[- ]?have|bestseller|sale|offer|"
    r"aw\d{2}|ss\d{2}|fw\d{2}|resort|capsule|collection|"
    r"men'?s|women'?s|mens|womens|unisex|ladies|gents"
    r")\b",
    re.IGNORECASE,
)
_PUNCT = re.compile(r"[|•·—–\-]{1,}|\s{2,}")

#: How each category should be worn. Gives the model the body region without
#: naming the body, which is what keeps the wording neutral.
_PLACEMENT = {
    GarmentCategory.UPPER: "worn on the upper body",
    GarmentCategory.LOWER: "worn on the lower body",
    GarmentCategory.DRESS: "worn as a full-length one-piece garment",
    GarmentCategory.OUTERWEAR: "worn as an open outer layer over the upper body",
    GarmentCategory.ACCESSORY: "worn as an accessory",
}

#: Applied ONLY to instruction-following image models. See the module note:
#: on masked VTON engines this text reaches nothing that controls the face.
_IDENTITY_DIRECTIVE = (
    "Replace only the clothing. Keep the person's face, hairline, hair, skin "
    "tone, body shape, proportions, pose and hands exactly as they are in the "
    "source photograph — do not reshape, slim, smooth, retouch or re-age any "
    "of them. Keep the original background, framing and lighting direction. "
    "Reproduce the garment's true colour, pattern, print placement, texture "
    "and closures, and let it drape naturally with contact shadows where it "
    "meets the body. Do not add, remove or restyle any other item."
)


def _clean(text: Optional[str]) -> str:
    if not text:
        return ""
    stripped = _NOISE.sub(" ", text)
    stripped = _PUNCT.sub(" ", stripped)
    return " ".join(stripped.split()).strip(" ,.")


def _dedupe_words(text: str) -> str:
    """Drop case-insensitive repeated WORDS, preserving order.

    Deduplicating whole phrases is not enough: colour="Silk" plus a title
    containing "Silk" yielded "Crimson Silk Silk Slip Column Maxi Dress".
    A repeated adjective reads to a diffusion model as emphasis, so the
    duplicate actively skews the render.
    """
    seen: set[str] = set()
    out: list[str] = []
    for word in text.split():
        key = word.lower().strip(",.")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(word)
    return " ".join(out)


def garment_description(
    *,
    title: Optional[str] = None,
    category: Optional[GarmentCategory] = None,
    colour: Optional[str] = None,
    material: Optional[str] = None,
    max_chars: int = 180,
) -> str:
    """A short, literal description of the GARMENT for a masked VTON engine.

    Colour and material lead because they are the attributes these models
    most often lose; the cleaned title supplies the silhouette. Truncated on
    a word boundary — a description cut mid-word is worse than a shorter one.
    """
    parts = [p for p in (_clean(colour), _clean(material), _clean(title)) if p]
    description = _dedupe_words(" ".join(parts))
    if category is not None and category in _PLACEMENT:
        description = f"{description}, {_PLACEMENT[category]}".strip(", ")
    if not description:
        # Never send an empty string: some Spaces treat it as "describe
        # anything" and drift. A neutral noun is safer than nothing.
        description = "garment"
    if len(description) > max_chars:
        description = description[:max_chars].rsplit(" ", 1)[0].rstrip(" ,")
    return description


def identity_directive() -> str:
    """The fixed identity-preservation instruction, verbatim and stable.

    Returned as a constant so it is identical on every call and every engine
    that can actually act on it. Not applied to masked VTON engines, where it
    would be inert text.
    """
    return _IDENTITY_DIRECTIVE


def build_edit_prompt(
    *,
    title: Optional[str] = None,
    category: Optional[GarmentCategory] = None,
    colour: Optional[str] = None,
    material: Optional[str] = None,
) -> str:
    """Full instruction for an instruction-following image model.

    Shape: what to put on, then the identity constraints. The garment comes
    first because these models weight early tokens more heavily, and the
    garment is the only thing that should change.
    """
    garment = garment_description(
        title=title, category=category, colour=colour, material=material
    )
    return (
        f"Dress the person in the reference photograph in this garment: {garment}. "
        f"{identity_directive()}"
    )
