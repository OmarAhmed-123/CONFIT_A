"""Deterministic styling constraints: an explicit anchor garment, and the
photo-derived palette used as a scoring preference.

HARD vs PREFERENCE (kept separate on purpose):
* ANCHOR (hard): "build around my navy trousers" means the looks MUST contain a
  catalogue bottom of that colour. If none exists, the composer says so.
* PALETTE (preference): pixel-supported colours from the photos raise or lower
  candidate scores through ColorHarmonyEngine. They never exclude a product.

Only pixel-supported colour families are passed in (see stylist_service), so a
colour the model merely guessed cannot steer the selection.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Optional

from backend.app.services.styling.color_harmony import ColorHarmonyEngine

#: English bottom-garment words that can be anchored. Arabic is not parsed here
#: (recorded as a limitation); an Arabic request simply has no anchor.
_BOTTOM_WORDS = r"(?:trousers|trouser|pants|chinos|jeans|skirt|shorts)"
_ANCHOR_CUE = r"(?:around|anchor(?:ed)?|with my|using my|match my|go with my|goes with my|pair with my|build (?:it |this |an outfit |a look )?around)"
_COLOUR_WORDS = ("navy", "black", "white", "grey", "gray", "charcoal", "beige", "brown",
                 "olive", "green", "blue", "red", "burgundy", "cream", "tan", "camel")

_ANCHOR_RE = re.compile(
    rf"(?:{_ANCHOR_CUE})\s+(?:(?:these|this|that|my|the|your|a|an)\s+)?"
    rf"(?:(?P<colour>{'|'.join(_COLOUR_WORDS)})\s+)?(?P<garment>{_BOTTOM_WORDS})(?!\w)"
)


def parse_anchor(prompt: str) -> Optional[Dict[str, str]]:
    """Return {"slot": "bottom", "garment": ..., "colour": ...} when the prompt names
    an anchor garment with a cue ("around", "with my", ...). Otherwise None.

    A bare "navy trousers" without a cue is NOT an anchor; it is only a colour
    preference, which keeps the hard constraint limited to explicit requests.
    """
    m = _ANCHOR_RE.search((prompt or "").lower())
    if not m:
        return None
    colour = m.group("colour")
    if colour == "gray":
        colour = "grey"
    return {"slot": "bottom", "garment": m.group("garment"), "colour": colour}


def anchor_matches(product: Any, anchor: Dict[str, str]) -> bool:
    """A catalogue product satisfies the anchor when its colour family names the
    requested colour (or the anchor has no colour), and its title names the garment
    family. Matching is on real product fields only."""
    colour = (anchor.get("colour") or "").lower()
    family = (getattr(product, "color_family", "") or "").lower()
    title = (getattr(product, "title", "") or "").lower()
    garment = anchor.get("garment", "")
    garment_root = {"trouser": "trousers", "trousers": "trousers", "pants": "trousers",
                    "chinos": "trousers", "jeans": "jeans", "skirt": "skirt", "shorts": "shorts"}.get(garment, garment)
    if garment_root not in title and not (garment_root == "trousers" and "trouser" in title):
        return False
    if colour and colour not in family:
        return False
    return True


def palette_bonus(product_colour: str, palette_families: Iterable[str]) -> float:
    """Score adjustment for a product colour against the photo palette.

    Per pixel-supported photo colour:
      * +12 when the product colour names the same colour (e.g. "olive" and
        "Olive Green"): the photo's colour is reinforced;
      * +8 when ColorHarmonyEngine says the pair harmonises (neutrals pair with
        everything, so a neutral product is never penalised for being neutral);
      * -8 when the engine says it clashes;
      * 0 when the engine is undecided.
    The total is capped to +/-20 so colour refines a choice without overriding
    category, occasion, or anchor constraints.
    """
    pc = (product_colour or "").lower().strip()
    total = 0.0
    for fam in palette_families or []:
        f = (fam or "").lower().strip()
        if not pc or not f:
            continue
        if f in pc or pc in f:
            total += 12.0
            continue
        verdict = ColorHarmonyEngine._pairs_harmonize(pc, f)
        if verdict is True:
            total += 8.0
        elif verdict is False:
            total -= 8.0
    return max(-20.0, min(20.0, total))
