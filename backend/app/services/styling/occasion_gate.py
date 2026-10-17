"""Hard occasion gate for catalogue candidates.

The composer used to treat occasion only as a score bonus, so an evening tuxedo
could still be selected for a "work" request. This gate is a deterministic
EXCLUSION rule, applied before any outfit is built:

* A product whose ``occasion_tags`` are all non-empty and contain none of the
  target occasion's tags is excluded (it was catalogued for other occasions only).
* A product with NO occasion tags is not excluded: the catalogue does not say
  it is unsuitable, and dropping it would silently shrink the catalogue.
* An unstated or unknown occasion applies no gate.

The tag sets come from the catalogue vocabulary (see the seed data). They are
data-driven matching on catalogue metadata, not canned answers.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional, Tuple

#: Occasion label -> catalogue occasion tags that make a product suitable.
OCCASION_TAGS: Dict[str, frozenset] = {
    "Work & Business": frozenset({"work", "business", "office"}),
    "Formal & Wedding": frozenset({"wedding", "formal", "black_tie", "gala"}),
    "Evening & Party": frozenset({"party", "dinner", "gala", "black_tie", "wedding"}),
    "Casual Weekend": frozenset({"casual", "weekend", "travel"}),
}


def _tags(product: Any) -> List[str]:
    raw = getattr(product, "occasion_tags", None)
    if raw is None and isinstance(product, dict):
        raw = product.get("occasion_tags")
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "[]")
        except (ValueError, TypeError):
            return []
    return [str(t).strip().lower() for t in raw if str(t).strip()]


def is_suitable(product: Any, occasion: Optional[str]) -> bool:
    wanted = OCCASION_TAGS.get(occasion or "")
    if not wanted:
        return True
    tags = _tags(product)
    if not tags:
        return True
    return bool(wanted.intersection(tags))


def gate_products(products: Iterable[Any], occasion: Optional[str]) -> Tuple[List[Any], List[str]]:
    """Return (kept products, excluded product ids). Order is preserved."""
    kept: List[Any] = []
    excluded: List[str] = []
    for p in products:
        if is_suitable(p, occasion):
            kept.append(p)
        else:
            excluded.append(str(getattr(p, "id", None) if not isinstance(p, dict) else p.get("id")))
    return kept, excluded
