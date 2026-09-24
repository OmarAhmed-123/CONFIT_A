"""Is the "alternative" outfit actually an alternative?

THE DEFECT THIS CLOSES (measured 2026-09-24)
``POST /api/v1/stylist/chat`` returned two looks for the same request:

    look 101  "The Evening & Party Silk Column Silhouette"  items=[3, 4, 6]  $505
    look 102  "The Modern Tonal Evening & Party Look"       items=[3, 4, 6]  $505

Same three products, two different invented titles, ``composition_warnings: []``,
and the code describes look 2 as "DIVERSE & NON-OVERLAPPING". The shopper is told
they are being offered an alternative when they are being offered the same thing
twice. That is a business-logic honesty defect, not a styling-taste issue.

ROOT CAUSE
When the alternate pools were empty (a small catalogue, or a look that consumed the
only product in a slot), every ``alt_*`` line fell back to ``slot_map[...][0]`` —
which is exactly what look 1 selected. The fallback produced an identical product
set, and nothing compared the two sets before publishing the second one.

THE RULE
    An outfit may only be presented as an alternative if its product set is
    sufficiently different from every already-presented look.

WHY JACCARD OVERLAP, AND WHY 0.5
--------------------------------
* Duplicate detection between recommendation sets is conventionally measured with
  a set-similarity coefficient; Jaccard (intersection / union) is the standard
  choice for discrete item sets and is what the literature uses to define
  "duplicated recommendations" (see the research record in the cycle report).
* Exact set equality would be too weak: an alternative sharing 3 of 4 items is not
  a different option to a shopper, it is the same option with one swap.
* Category-count heuristics ("no more than two black shirts") do not fit here: an
  outfit is *supposed* to contain one item per slot, so category diversity is
  structurally satisfied while the shopper still sees the identical three products.
* Threshold 0.5 means: fewer than half the union may be shared. For two 4-item
  looks that allows sharing up to ~2 items (e.g. the same shoes) while rejecting a
  full overlap, which is the behaviour a stylist would defend.
* The threshold is a parameter, not a buried literal, so it can be tuned with
  evidence instead of by editing a comparison.

SCOPE NOTE
This module decides *distinctness only*. It never re-ranks, never invents items
and never removes items from a look that is already distinct.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence, Set

#: Maximum Jaccard overlap between two presented looks. 0.5 == "at most half the
#: pooled products may be shared". See the module docstring for the reasoning.
MIN_DISTINCTNESS_OVERLAP = 0.5


def product_ids(outfit: Dict[str, Any]) -> Set[Any]:
    """The product set behind a composed outfit.

    Reads ``product_id`` from each item. Items without an id are ignored: an
    unknown id must not make two looks look different by accident.
    """
    ids: Set[Any] = set()
    for item in outfit.get("items") or []:
        pid = item.get("product_id")
        if pid is not None:
            ids.add(pid)
    return ids


def jaccard(a: Iterable[Any], b: Iterable[Any]) -> float:
    """|A ∩ B| / |A ∪ B|; two empty sets are defined as 0.0 (no evidence)."""
    sa, sb = set(a), set(b)
    union = sa | sb
    if not union:
        return 0.0
    return len(sa & sb) / len(union)


def overlap_with_presented(candidate: Dict[str, Any], presented: Sequence[Dict[str, Any]]) -> float:
    """Highest overlap between the candidate and any already-presented look."""
    ids = product_ids(candidate)
    return max((jaccard(ids, product_ids(o)) for o in presented), default=0.0)


def is_distinct(
    candidate: Dict[str, Any],
    presented: Sequence[Dict[str, Any]],
    threshold: float = MIN_DISTINCTNESS_OVERLAP,
) -> bool:
    """True when the candidate may be shown as an alternative of `presented`.

    A candidate with NO resolvable product ids is rejected: distinctness cannot be
    established, and publishing an unverifiable "alternative" is the defect.
    An empty `presented` list accepts any candidate that has products.
    """
    if not product_ids(candidate):
        return False
    if not presented:
        return True
    return overlap_with_presented(candidate, presented) < threshold


def suppression_reason(
    candidate: Dict[str, Any],
    presented: Sequence[Dict[str, Any]],
    threshold: float = MIN_DISTINCTNESS_OVERLAP,
) -> str:
    """A message that states the fact, for the API payload and for logs."""
    overlap = overlap_with_presented(candidate, presented)
    return (
        f"alternative suppressed: {int(round(overlap * 100))}% product-set overlap with an "
        f"already-presented look (limit {int(threshold * 100)}%) — the same products were "
        f"not offered twice"
    )


def items_for_display(outfit: Dict[str, Any]) -> List[Any]:
    """Small helper for callers that want the shared ids (diagnostics/tests)."""
    return sorted(product_ids(outfit), key=lambda v: str(v))
