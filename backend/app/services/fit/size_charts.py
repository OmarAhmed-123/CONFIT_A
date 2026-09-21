"""Size-chart resolution: which body-girth table applies to THIS product.

Audit findings this closes
--------------------------
* "لم يتحقق من اختلاف جداول المقاسات بين البراندات" — brand-to-brand chart
  differences were never handled: the old engine printed the same
  92–96 / 96–102 / 102–108 cm table for every product of every brand, and
  claimed "True to standard international sizing" for brands nobody had
  measured.
* "ولا من أن النتيجة لا تُعرض عند غياب inventory/size chart" — a recommendation
  was produced even when the product had no size chart and no sellable sizes.

Resolution order (first source that yields a usable chart wins)
---------------------------------------------------------------
1. ``ProductChartSource``  — the product's own ``size_chart_json``, authored by
   the brand. This is the only *authoritative* source: it is the brand's own
   published body-measurement table.
2. ``StandardChartSource`` — the EN 13402-3 letter-code body-girth ranges
   (chest/bust girth per letter code, with waist and hip derived from the
   standard's paired secondary dimensions). Used ONLY to cover the sizes the
   product actually sells, and always reported as provenance="standard_en13402"
   so the UI can say the chart is a public standard, not the brand's own.
3. Nothing — ``SizeChartResolver.resolve`` returns a chart with
   ``rows == []`` and the engine refuses to recommend.

Provenance and freshness are first-class: every chart carries where it came
from and, for brand charts, when it was last updated, because the audit asked
for exactly that ("اعرض القياسات المستخدمة ومصدر جدول المقاس وتاريخ تحديثه").

Chart JSON contract (``products.size_chart_json``)
--------------------------------------------------
Two accepted shapes, both validated; anything else is ignored with a recorded
reason rather than silently half-parsed::

    // A) explicit rows
    {
      "unit": "cm",                       // "cm" (default) or "in"
      "measurement_type": "body",         // "body" (default) or "garment"
      "updated_at": "2026-08-01",
      "size_system": "EU",
      "rows": [
        {"size": "S", "chest": [88, 94], "waist": [74, 80], "hip": [90, 96]},
        {"size": "M", "chest": [94, 100], "waist": [80, 86], "hip": [96, 102]}
      ]
    }

    // B) size-keyed map (common in imported catalogues)
    {
      "unit": "in",
      "sizes": {
        "S": {"chest": "35-37", "waist": "29-31"},
        "M": {"chest": "38-40", "waist": "32-34"}
      }
    }

Both point ("chest": 96) and range ("chest": [94, 100]) values are supported; a
point value is expanded to a symmetric range using the size-step for that
dimension so the scorer always has an interval to work with.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence, Tuple

from backend.app.services.fit.units import CM_PER_IN

# Dimensions the scorer understands, in the order they are reported.
DIMENSIONS: Tuple[str, ...] = ("chest", "waist", "hip", "shoulder", "inseam", "neck")

# Aliases seen in real catalogue exports -> canonical dimension name.
_DIMENSION_ALIASES: Dict[str, str] = {
    "chest": "chest", "bust": "chest", "chest_cm": "chest", "bust_cm": "chest",
    "chest_girth": "chest", "bust_girth": "chest",
    "waist": "waist", "waist_cm": "waist", "waist_girth": "waist", "natural_waist": "waist",
    "hip": "hip", "hips": "hip", "hip_cm": "hip", "hip_girth": "hip", "seat": "hip",
    "shoulder": "shoulder", "shoulders": "shoulder", "shoulder_cm": "shoulder",
    "shoulder_width": "shoulder", "across_shoulder": "shoulder",
    "inseam": "inseam", "inside_leg": "inseam", "inseam_cm": "inseam",
    "neck": "neck", "neck_cm": "neck", "neck_girth": "neck", "collar": "neck",
}

# Default half-width (cm) applied when a chart gives a single point value.
_POINT_HALF_WIDTH_CM: Dict[str, float] = {
    "chest": 2.0, "waist": 2.0, "hip": 2.0, "shoulder": 0.75, "inseam": 1.5, "neck": 0.5,
}

# EN 13402-3 letter-code CHEST/BUST girth ranges (cm). Public standard; used as
# the fallback body chart when a brand publishes none.
# Source: EN 13402-3 letter-code table (men's chest girth / women's bust girth).
_EN13402_CHEST_MEN: Dict[str, Tuple[float, float]] = {
    "XXS": (70, 78), "XS": (78, 86), "S": (86, 94), "M": (94, 102),
    "L": (102, 110), "XL": (110, 118), "XXL": (118, 129), "3XL": (129, 141),
    "4XL": (141, 154), "5XL": (154, 166),
}
_EN13402_BUST_WOMEN: Dict[str, Tuple[float, float]] = {
    "XXS": (66, 74), "XS": (74, 82), "S": (82, 90), "M": (90, 98),
    "L": (98, 107), "XL": (107, 119), "XXL": (119, 131), "3XL": (131, 143),
    "4XL": (143, 155), "5XL": (155, 167),
}
# EN 13402-3 pairs a chest girth with a secondary waist girth (men: the "G"/"F"
# waist alternatives run ~14–18 cm below chest through the core sizes) and, for
# women, a hip girth. These offsets reproduce the standard's paired values for
# the mid-range sizes and are applied consistently across the letter codes.
_STANDARD_WAIST_OFFSET_MEN = -14.0
_STANDARD_HIP_OFFSET_MEN = -2.0
_STANDARD_WAIST_OFFSET_WOMEN = -18.0
_STANDARD_HIP_OFFSET_WOMEN = +6.0

# Canonical ordering so "one size up" is a well-defined operation.
_LETTER_ORDER: Tuple[str, ...] = (
    "XXXS", "XXS", "XS", "S", "S/M", "M", "M/L", "L", "XL", "XXL", "3XL", "4XL", "5XL",
)
_LETTER_NORMALISE: Dict[str, str] = {
    "2XS": "XXS", "XXSMALL": "XXS", "EXTRA EXTRA SMALL": "XXS",
    "XSMALL": "XS", "EXTRA SMALL": "XS", "X-SMALL": "XS",
    "SMALL": "S", "MEDIUM": "M", "LARGE": "L",
    "XLARGE": "XL", "X-LARGE": "XL", "EXTRA LARGE": "XL",
    "2XL": "XXL", "XXLARGE": "XXL", "XX-LARGE": "XXL",
    "3X": "3XL", "XXXL": "3XL", "4X": "4XL", "XXXXL": "4XL", "5X": "5XL",
}


def normalise_size_label(raw: str) -> str:
    """'x-large' -> 'XL', ' 32x30 ' -> '32X30'. Numeric labels pass through."""
    token = re.sub(r"\s+", " ", str(raw or "")).strip().upper()
    compact = token.replace(" ", "").replace("_", "")
    return _LETTER_NORMALISE.get(token, _LETTER_NORMALISE.get(compact, compact or token))


def size_sort_key(label: str) -> Tuple[int, float, str]:
    """Order sizes smallest -> largest across letter, numeric and WxL labels."""
    norm = normalise_size_label(label)
    if norm in _LETTER_ORDER:
        return (0, float(_LETTER_ORDER.index(norm)), norm)
    m = re.match(r"^(\d+(?:\.\d+)?)", norm)
    if m:
        return (1, float(m.group(1)), norm)
    return (2, 0.0, norm)


class ChartParseError(ValueError):
    pass


# ── value objects ──────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SizeRow:
    """One size of a chart: body-girth ranges in centimetres."""

    size: str
    ranges: Dict[str, Tuple[float, float]]   # dimension -> (min_cm, max_cm)

    def midpoint(self, dimension: str) -> Optional[float]:
        rng = self.ranges.get(dimension)
        return None if rng is None else round((rng[0] + rng[1]) / 2.0, 1)

    def covers(self, dimension: str, value_cm: float) -> bool:
        rng = self.ranges.get(dimension)
        return rng is not None and rng[0] <= value_cm <= rng[1]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "size": self.size,
            "ranges_cm": {k: [v[0], v[1]] for k, v in sorted(self.ranges.items())},
        }


@dataclass(frozen=True)
class ChartProvenance:
    """Where the chart came from, and how much it can be trusted."""

    # "brand_published"        — the brand's own published chart
    # "product_chart_derived"  — a chart attached to this product but derived
    #                            from a stated external source (see `standard`)
    # "standard_en13402"       — engine fallback to the public standard
    # "none"                   — no chart; the engine must refuse
    source: str
    label: str                        # human-readable, shown in the UI
    updated_at: Optional[str] = None  # ISO date of the brand chart, if known
    standard: Optional[str] = None    # e.g. "EN 13402-3"
    measurement_type: str = "body"    # "body" | "garment"
    notes: Tuple[str, ...] = ()

    @property
    def is_authoritative(self) -> bool:
        """True only for a chart the brand itself published.

        A product-specific chart derived from a standard is better than the
        generic fallback, but it is NOT the brand's word, and the UI must not
        present it as such.
        """
        return self.source == "brand_published"

    @property
    def is_product_specific(self) -> bool:
        """True when the chart came from this product rather than the fallback."""
        return self.source in ("brand_published", "product_chart_derived")

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "label": self.label,
            "updated_at": self.updated_at,
            "standard": self.standard,
            "measurement_type": self.measurement_type,
            "is_brand_published": self.is_authoritative,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class SizeChart:
    rows: Tuple[SizeRow, ...]
    provenance: ChartProvenance
    size_system: Optional[str] = None
    parse_warnings: Tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.rows)

    @property
    def dimensions(self) -> Tuple[str, ...]:
        present = {d for row in self.rows for d in row.ranges}
        return tuple(d for d in DIMENSIONS if d in present)

    def restricted_to(self, sizes: Iterable[str]) -> "SizeChart":
        """Keep only the sizes the product actually sells (inventory gate)."""
        wanted = {normalise_size_label(s) for s in sizes}
        if not wanted:
            return SizeChart((), self.provenance, self.size_system, self.parse_warnings)
        kept = tuple(r for r in self.rows if normalise_size_label(r.size) in wanted)
        return SizeChart(kept, self.provenance, self.size_system, self.parse_warnings)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "provenance": self.provenance.as_dict(),
            "size_system": self.size_system,
            "dimensions": list(self.dimensions),
            "rows": [r.as_dict() for r in self.rows],
            "parse_warnings": list(self.parse_warnings),
        }


# ── parsing helpers ────────────────────────────────────────────────────────
def _to_cm(value: float, unit: str) -> float:
    return round(value * (CM_PER_IN if unit == "in" else 1.0), 1)


_RANGE_RE = re.compile(
    r"^\s*(\d+(?:[.,]\d+)?)\s*(?:-|–|—|to|\.\.)\s*(\d+(?:[.,]\d+)?)\s*$", re.IGNORECASE
)
_NUM_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(?:cm|in|\")?\s*$", re.IGNORECASE)


def _parse_dimension_value(
    raw: Any, dimension: str, unit: str
) -> Optional[Tuple[float, float]]:
    """Accept 96, "96", "94-100", [94, 100], {"min":94,"max":100} -> (min,max) cm."""
    if raw is None:
        return None

    lo = hi = None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        lo = hi = float(raw)
    elif isinstance(raw, (list, tuple)) and len(raw) == 2:
        try:
            lo, hi = float(raw[0]), float(raw[1])
        except (TypeError, ValueError):
            return None
    elif isinstance(raw, dict):
        try:
            lo = float(raw.get("min", raw.get("from")))  # type: ignore[arg-type]
            hi = float(raw.get("max", raw.get("to")))    # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
    elif isinstance(raw, str):
        m = _RANGE_RE.match(raw)
        if m:
            lo, hi = float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", "."))
        else:
            m = _NUM_RE.match(raw)
            if not m:
                return None
            lo = hi = float(m.group(1).replace(",", "."))
    else:
        return None

    if lo is None or hi is None:
        return None
    if lo <= 0 or hi <= 0:
        return None
    lo_cm, hi_cm = _to_cm(lo, unit), _to_cm(hi, unit)
    if lo_cm == hi_cm:
        half = _POINT_HALF_WIDTH_CM.get(dimension, 2.0)
        lo_cm, hi_cm = round(lo_cm - half, 1), round(hi_cm + half, 1)
    if hi_cm < lo_cm:
        lo_cm, hi_cm = hi_cm, lo_cm
    # A body girth outside this window is a unit error in the chart, not a size.
    if not (20.0 <= lo_cm <= 250.0 and 20.0 <= hi_cm <= 250.0):
        return None
    return (lo_cm, hi_cm)


def _normalise_unit(raw: Any) -> str:
    token = str(raw or "cm").strip().lower()
    if token in {"in", "inch", "inches", '"'}:
        return "in"
    return "cm"


def _normalise_updated_at(raw: Any) -> Optional[str]:
    if raw in (None, ""):
        return None
    if isinstance(raw, (date, datetime)):
        return raw.isoformat()[:10]
    text = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[: len(fmt) + 2], fmt).date().isoformat()
        except ValueError:
            continue
    return text[:32] or None


def parse_size_chart_json(raw: Any) -> SizeChart:
    """Parse ``products.size_chart_json`` into a validated SizeChart.

    Never raises on malformed brand data: an unusable chart yields an EMPTY
    chart plus the reason in ``parse_warnings``, so the engine refuses to
    recommend instead of inventing a table.
    """
    warnings: List[str] = []

    if isinstance(raw, str):
        text = raw.strip()
        if not text or text in {"{}", "[]", "null"}:
            return SizeChart((), ChartProvenance("none", "No brand size chart published"))
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            return SizeChart(
                (),
                ChartProvenance("none", "No usable brand size chart"),
                parse_warnings=("size_chart_json is not valid JSON",),
            )
    else:
        data = raw

    if not isinstance(data, dict) or not data:
        return SizeChart((), ChartProvenance("none", "No brand size chart published"))

    unit = _normalise_unit(data.get("unit") or data.get("units"))
    measurement_type = str(data.get("measurement_type") or "body").strip().lower()
    if measurement_type not in {"body", "garment"}:
        measurement_type = "body"
    updated_at = _normalise_updated_at(data.get("updated_at") or data.get("last_updated"))
    size_system = (str(data.get("size_system")).strip() if data.get("size_system") else None)

    raw_rows: List[Tuple[str, Dict[str, Any]]] = []
    if isinstance(data.get("rows"), list):
        for item in data["rows"]:
            if isinstance(item, dict) and item.get("size") is not None:
                raw_rows.append((str(item["size"]), item))
    elif isinstance(data.get("sizes"), dict):
        for label, item in data["sizes"].items():
            if isinstance(item, dict):
                raw_rows.append((str(label), item))
    else:
        # Bare {"S": {...}, "M": {...}} map.
        for label, item in data.items():
            if isinstance(item, dict) and any(
                _DIMENSION_ALIASES.get(str(k).strip().lower()) for k in item
            ):
                raw_rows.append((str(label), item))

    if not raw_rows:
        return SizeChart(
            (),
            ChartProvenance("none", "No usable brand size chart"),
            parse_warnings=("size_chart_json contains no recognisable size rows",),
        )

    rows: List[SizeRow] = []
    seen: set[str] = set()
    for label, item in raw_rows:
        size = normalise_size_label(label)
        if not size or size in seen:
            continue
        ranges: Dict[str, Tuple[float, float]] = {}
        for key, value in item.items():
            dim = _DIMENSION_ALIASES.get(str(key).strip().lower())
            if dim is None:
                continue
            parsed = _parse_dimension_value(value, dim, unit)
            if parsed is None:
                if value not in (None, ""):
                    warnings.append(f"size {size}: unreadable {dim} value {value!r}")
                continue
            ranges[dim] = parsed
        if ranges:
            rows.append(SizeRow(size=size, ranges=ranges))
            seen.add(size)
        else:
            warnings.append(f"size {label}: no readable measurements")

    if not rows:
        return SizeChart(
            (),
            ChartProvenance("none", "No usable brand size chart"),
            parse_warnings=tuple(warnings) or ("no size row carried a readable measurement",),
        )

    rows.sort(key=lambda r: size_sort_key(r.size))
    note_list: List[str] = []
    if measurement_type == "garment":
        note_list.append(
            "Chart lists finished-garment measurements; the engine compares them to "
            "body girth including the garment's ease allowance."
        )

    # A chart attached to a product is not automatically a chart the BRAND
    # published. A chart may declare its own origin (e.g. one derived from a
    # public standard for a catalogue whose brands publish nothing), and if it
    # does we must repeat that claim rather than upgrade it to
    # "brand-published" — the provenance card is the user's only way to judge
    # how much to trust the number, so overstating it here is the same class of
    # fabrication this engine was written to remove.
    declared_source = data.get("source")
    declared_standard = data.get("standard")
    is_derived = bool(declared_source) and not bool(data.get("published_by_brand"))
    for note in data.get("notes") or ():
        if isinstance(note, str) and note.strip():
            note_list.append(note.strip())

    if is_derived:
        provenance = ChartProvenance(
            source="product_chart_derived",
            label=f"Product size chart — derived from {declared_source}",
            updated_at=updated_at,
            standard=str(declared_standard) if declared_standard else str(declared_source),
            measurement_type=measurement_type,
            notes=tuple(note_list),
        )
    else:
        provenance = ChartProvenance(
            source="brand_published",
            label="Brand-published size chart",
            updated_at=updated_at,
            standard=str(declared_standard) if declared_standard else None,
            measurement_type=measurement_type,
            notes=tuple(note_list),
        )

    return SizeChart(
        rows=tuple(rows),
        provenance=provenance,
        size_system=size_system,
        parse_warnings=tuple(warnings),
    )


def standard_chart(
    sizes: Sequence[str], *, demographic: str = "unisex"
) -> SizeChart:
    """EN 13402-3 letter-code body chart, limited to ``sizes``.

    Only letter-coded sizes can be resolved this way — the standard defines
    letter codes against chest/bust girth. A numeric or WxL size has no
    standards mapping without the brand's own chart, so it is omitted (and the
    engine will refuse rather than guess).
    """
    demo = (demographic or "unisex").strip().lower()
    if demo in {"women", "woman", "female", "womens", "women's"}:
        table, waist_off, hip_off = _EN13402_BUST_WOMEN, _STANDARD_WAIST_OFFSET_WOMEN, _STANDARD_HIP_OFFSET_WOMEN
        label = "EN 13402-3 letter-code chart (women's bust girth)"
    else:
        table, waist_off, hip_off = _EN13402_CHEST_MEN, _STANDARD_WAIST_OFFSET_MEN, _STANDARD_HIP_OFFSET_MEN
        label = "EN 13402-3 letter-code chart (men's/unisex chest girth)"

    rows: List[SizeRow] = []
    skipped: List[str] = []
    for raw in sizes:
        size = normalise_size_label(raw)
        band = table.get(size)
        if band is None:
            skipped.append(size)
            continue
        chest = (float(band[0]), float(band[1]))
        rows.append(
            SizeRow(
                size=size,
                ranges={
                    "chest": chest,
                    "waist": (round(chest[0] + waist_off, 1), round(chest[1] + waist_off, 1)),
                    "hip": (round(chest[0] + hip_off, 1), round(chest[1] + hip_off, 1)),
                },
            )
        )

    if not rows:
        return SizeChart(
            (),
            ChartProvenance("none", "No size chart available for this product"),
            parse_warnings=(
                "no sellable size could be mapped to the EN 13402-3 letter codes"
                + (f" (unmapped: {', '.join(sorted(set(skipped)))})" if skipped else ""),
            ),
        )

    rows.sort(key=lambda r: size_sort_key(r.size))
    notes = [
        "Public standard, not this brand's own measurements: treat it as an "
        "approximation and prefer the brand's chart when published.",
    ]
    if skipped:
        notes.append(
            "Sizes without a standards mapping were excluded: " + ", ".join(sorted(set(skipped)))
        )
    return SizeChart(
        rows=tuple(rows),
        provenance=ChartProvenance(
            source="standard_en13402",
            label=label,
            standard="EN 13402-3",
            measurement_type="body",
            notes=tuple(notes),
        ),
        size_system="EU",
    )


# ── strategy: pluggable chart sources ──────────────────────────────────────
class ChartSource(Protocol):
    """A place a size chart can come from (strategy pattern).

    Adding a new source (a brand-level default chart, a supplier feed, a
    per-category house chart) means adding one class here — the scoring engine
    never changes.
    """

    name: str

    def load(self, context: "ChartContext") -> Optional[SizeChart]: ...


@dataclass
class ChartContext:
    """Everything a source may need to resolve a chart."""

    product_size_chart_json: Any = None
    sellable_sizes: Sequence[str] = field(default_factory=tuple)
    demographic: str = "unisex"
    brand_name: Optional[str] = None
    category_slug: Optional[str] = None


class ProductChartSource:
    name = "product_size_chart_json"

    def load(self, context: ChartContext) -> Optional[SizeChart]:
        chart = parse_size_chart_json(context.product_size_chart_json)
        if chart.rows:
            return chart
        # Return the EMPTY chart (rather than None) when the brand published
        # something we could not read: the resolver must carry that warning
        # forward so the next source's answer is visibly a fallback, not a
        # clean brand match. Silently swallowing it is how "the brand chart is
        # broken" became invisible in production.
        return chart if chart.parse_warnings else None


class StandardChartSource:
    name = "en13402_standard"

    def load(self, context: ChartContext) -> Optional[SizeChart]:
        if not context.sellable_sizes:
            return None
        chart = standard_chart(context.sellable_sizes, demographic=context.demographic)
        return chart if chart.rows else None


class SizeChartResolver:
    """Resolve the best available chart, restricted to sellable sizes.

    The restriction is the inventory gate the audit asked for: a size the
    product does not sell can never be recommended, whatever the chart says.
    """

    def __init__(self, sources: Optional[Sequence[ChartSource]] = None):
        self.sources: Tuple[ChartSource, ...] = tuple(
            sources if sources is not None else (ProductChartSource(), StandardChartSource())
        )

    def resolve(self, context: ChartContext) -> SizeChart:
        collected_warnings: List[str] = []
        for source in self.sources:
            chart = source.load(context)
            if chart is None:
                continue
            if not chart.rows:
                collected_warnings.extend(chart.parse_warnings)
                continue
            collected_warnings.extend(chart.parse_warnings)
            if context.sellable_sizes:
                restricted = chart.restricted_to(context.sellable_sizes)
                if not restricted.rows:
                    collected_warnings.append(
                        f"{source.name}: chart covers no size this product currently sells"
                    )
                    continue
                if len(restricted.rows) < len(chart.rows):
                    collected_warnings.append(
                        "sizes present in the chart but not sellable were excluded"
                    )
                chart = restricted
            return SizeChart(
                rows=chart.rows,
                provenance=chart.provenance,
                size_system=chart.size_system,
                parse_warnings=tuple(dict.fromkeys(collected_warnings)),
            )

        return SizeChart(
            rows=(),
            provenance=ChartProvenance(
                source="none",
                label="No size chart available for this product",
            ),
            parse_warnings=tuple(dict.fromkeys(collected_warnings)),
        )
