"""Outfit composition policy — the single source of truth for what a *valid*
saved outfit is, and in what order its layers stack.

Why this module exists
----------------------
Before OUTFIT-02 the rules were scattered and partly absent:

* ``OutfitService.save_outfit`` accepted ANY set of SKUs. Two pairs of shoes,
  three trousers, a duplicated SKU, or a 60-item payload all persisted happily.
* ``sort_order`` was written as the *arrival index* of the request list, so the
  canvas rendered "shoes, blazer, shirt" if that is how the client happened to
  post them. There was no layer semantics anywhere.
* The frontend had its own ad-hoc category-string matcher, so client and server
  could disagree about which slot a product belongs to.

DRY: the slot classification itself still comes from ``styling.ontology`` (the
existing single ontology). This module only adds the *composition* rules on top
of it, and is imported by the service layer, the controllers and the tests, so
there is exactly one implementation of "is this outfit valid" in the codebase.

Design
------
Pure functions over plain data, no ORM and no I/O, so the policy is trivially
unit-testable and reusable from a worker or a CLI. Violations are returned as
structured, explainable objects (code + human message + offending positions)
rather than a bare bool — the audit explicitly required that the UI be able to
*show the reason* a combination was rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Sequence

# Canonical canvas positions. Keep in sync with OutfitItem.position and the
# frontend CanvasItem['slot'] union (asserted by a contract test).
POSITION_TOP = "top"
POSITION_BOTTOM = "bottom"
POSITION_OUTERWEAR = "outerwear"
POSITION_FOOTWEAR = "footwear"
POSITION_ACCESSORY = "accessory"
POSITION_DRESS = "dress"

CANVAS_POSITIONS: tuple[str, ...] = (
    POSITION_OUTERWEAR,
    POSITION_TOP,
    POSITION_DRESS,
    POSITION_BOTTOM,
    POSITION_FOOTWEAR,
    POSITION_ACCESSORY,
)

# Render/stacking order of the canvas, outermost layer first. This is what
# ``OutfitItem.sort_order`` stores, so any client that simply orders by
# sort_order gets a correct visual stack without re-deriving layer semantics.
LAYER_ORDER: Dict[str, int] = {
    POSITION_OUTERWEAR: 10,
    POSITION_TOP: 20,
    POSITION_DRESS: 25,
    POSITION_BOTTOM: 30,
    POSITION_FOOTWEAR: 40,
    POSITION_ACCESSORY: 50,
}

# How many items each position may hold in one saved outfit. Garment slots are
# exclusive (you wear one pair of trousers); accessories legitimately stack
# (belt + watch + pocket square) but are capped so the canvas stays a look and
# not a shopping list.
POSITION_CAPACITY: Dict[str, int] = {
    POSITION_OUTERWEAR: 1,
    POSITION_TOP: 1,
    POSITION_DRESS: 1,
    POSITION_BOTTOM: 1,
    POSITION_FOOTWEAR: 1,
    POSITION_ACCESSORY: 4,
}

MAX_ITEMS_PER_OUTFIT = 12

# An outfit is "wearable" when the body is actually covered: either a one-piece
# (dress/jumpsuit) or a top+bottom pair. Footwear is recommended, not required —
# users legitimately save upper-body combinations.
REQUIRED_EITHER: tuple[tuple[str, ...], ...] = (
    (POSITION_DRESS,),
    (POSITION_TOP, POSITION_BOTTOM),
)


@dataclass(frozen=True)
class Violation:
    """A single, explainable reason an outfit was rejected."""

    code: str
    message: str
    positions: tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["positions"] = list(self.positions)
        return d


@dataclass(frozen=True)
class CompositionVerdict:
    """Result of evaluating a candidate item set."""

    is_valid: bool
    violations: tuple[Violation, ...]
    warnings: tuple[str, ...]
    missing_positions: tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "violations": [v.to_dict() for v in self.violations],
            "warnings": list(self.warnings),
            "missing_positions": list(self.missing_positions),
        }

    @property
    def first_message(self) -> str:
        return self.violations[0].message if self.violations else ""


def sort_order_for(position: str, occurrence: int = 0) -> int:
    """Deterministic stacking index for a position.

    ``occurrence`` disambiguates the stackable accessory slot so two accessories
    keep a stable, reproducible relative order instead of depending on dict or
    request ordering.
    """
    return LAYER_ORDER.get(position, 60) + max(0, occurrence)


def order_items(items: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return items sorted into canonical layer order with sort_order assigned.

    Stable: items sharing a position keep their relative input order, so a user
    who arranges three accessories deliberately does not get them shuffled.
    """
    seen: Dict[str, int] = {}
    decorated: List[tuple[int, int, Dict[str, Any]]] = []
    for idx, item in enumerate(items):
        position = item.get("position") or POSITION_ACCESSORY
        occurrence = seen.get(position, 0)
        seen[position] = occurrence + 1
        order = sort_order_for(position, occurrence)
        enriched = {**item, "position": position, "sort_order": order}
        decorated.append((order, idx, enriched))
    decorated.sort(key=lambda t: (t[0], t[1]))
    return [d[2] for d in decorated]


def evaluate_composition(items: Sequence[Dict[str, Any]]) -> CompositionVerdict:
    """Validate a candidate outfit item set.

    ``items`` are dicts with at least ``position``; ``product_sku_id`` /
    ``product_id`` are used for duplicate detection when present.
    """
    violations: List[Violation] = []
    warnings: List[str] = []

    if not items:
        return CompositionVerdict(
            is_valid=False,
            violations=(
                Violation(
                    code="empty_outfit",
                    message="An outfit needs at least one real, purchasable item.",
                ),
            ),
            warnings=(),
            missing_positions=tuple(REQUIRED_EITHER[1]),
        )

    if len(items) > MAX_ITEMS_PER_OUTFIT:
        violations.append(
            Violation(
                code="too_many_items",
                message=(
                    f"An outfit can hold at most {MAX_ITEMS_PER_OUTFIT} pieces; "
                    f"{len(items)} were supplied."
                ),
            )
        )

    # Unknown positions would silently break canvas rendering downstream.
    unknown = sorted({
        str(i.get("position")) for i in items
        if i.get("position") not in CANVAS_POSITIONS
    })
    if unknown:
        violations.append(
            Violation(
                code="unknown_position",
                message=f"Unsupported canvas position(s): {', '.join(unknown)}.",
                positions=tuple(unknown),
            )
        )

    # Duplicate SKUs: saving the same SKU twice double-counts the price and
    # produces a look the user never composed.
    sku_ids = [i.get("product_sku_id") for i in items if i.get("product_sku_id")]
    if len(sku_ids) != len(set(sku_ids)):
        violations.append(
            Violation(
                code="duplicate_item",
                message="The same item was added twice — remove the duplicate.",
            )
        )

    # Same PRODUCT in two different SKUs (e.g. the same blazer in size M and L)
    # is the subtler version of the same bug: it passes a SKU-only check, but
    # nobody wears one garment twice and the outfit total silently doubles.
    product_ids = [i.get("product_id") for i in items if i.get("product_id")]
    if len(product_ids) != len(set(product_ids)):
        violations.append(
            Violation(
                code="duplicate_product",
                message=(
                    "The same garment was added more than once (different sizes "
                    "of one product) — keep a single size."
                ),
            )
        )

    # Capacity per position.
    counts: Dict[str, int] = {}
    for i in items:
        pos = i.get("position")
        if pos in CANVAS_POSITIONS:
            counts[pos] = counts.get(pos, 0) + 1
    over = [
        (pos, n) for pos, n in sorted(counts.items())
        if n > POSITION_CAPACITY.get(pos, 1)
    ]
    for pos, n in over:
        cap = POSITION_CAPACITY.get(pos, 1)
        violations.append(
            Violation(
                code="slot_over_capacity",
                message=(
                    f"The {pos} slot holds {cap} item(s), but {n} were supplied. "
                    f"Replace instead of stacking."
                ),
                positions=(pos,),
            )
        )

    # A one-piece and a separates pair are mutually exclusive outfits.
    if counts.get(POSITION_DRESS) and (
        counts.get(POSITION_TOP) or counts.get(POSITION_BOTTOM)
    ):
        violations.append(
            Violation(
                code="conflicting_layers",
                message=(
                    "A dress/one-piece cannot be combined with a separate top or "
                    "bottom. Remove one of them."
                ),
                positions=(POSITION_DRESS, POSITION_TOP, POSITION_BOTTOM),
            )
        )

    # Completeness: a warning, not a rejection — partial looks are savable, but
    # the user is told honestly what is missing instead of the UI implying a
    # complete outfit.
    missing = _missing_positions(counts)
    if missing:
        warnings.append(
            "This look is incomplete — missing: " + ", ".join(missing) + "."
        )
    elif not counts.get(POSITION_FOOTWEAR):
        warnings.append("Add footwear to complete the look.")

    return CompositionVerdict(
        is_valid=not violations,
        violations=tuple(violations),
        warnings=tuple(warnings),
        missing_positions=tuple(missing),
    )


def _missing_positions(counts: Dict[str, int]) -> List[str]:
    """Which positions are needed for a wearable look, given what is present."""
    for combo in REQUIRED_EITHER:
        if all(counts.get(p) for p in combo):
            return []
    # Report the cheapest path to wearability: complete the separates pair.
    return [p for p in (POSITION_TOP, POSITION_BOTTOM) if not counts.get(p)]


def completeness_status(counts_or_items: Iterable[Any]) -> str:
    """'complete_look' | 'partial_look' | 'empty' — one shared vocabulary."""
    items = list(counts_or_items)
    if not items:
        return "empty"
    if isinstance(items[0], dict):
        counts: Dict[str, int] = {}
        for i in items:
            pos = i.get("position")
            if pos:
                counts[pos] = counts.get(pos, 0) + 1
    else:  # already a mapping-like of position -> count
        counts = dict(counts_or_items)  # type: ignore[arg-type]
    if _missing_positions(counts):
        return "partial_look"
    return "complete_look" if counts.get(POSITION_FOOTWEAR) else "partial_look"
