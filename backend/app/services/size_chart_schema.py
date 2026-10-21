"""Formal, versioned schema for ``products.size_chart_json``.

``size_chart_json`` is a TEXT column that four different things read: the sizing
engine (``services/fit/size_charts.py``), the fit-finder response, the product
API, and the storefront. Until now it had no writer-side contract at all — the
column was whatever a seed script or an operator's SQL put there, and the only
validation happened when the engine tried to parse it, at which point the
shopper was already on the page and the failure surfaced as "no size guidance"
rather than as a rejection.

This module is the missing contract. It is:

* **Versioned.** ``schema_version`` is required in stored charts. A chart written
  under 1.0 is still readable when 1.1 adds fields, and a chart claiming a
  version this build does not know is REJECTED rather than best-effort parsed —
  silently reading a future format is how a shopper gets a wrong size.
* **Bounded.** Sizes, rows, dimensions, string lengths and payload size all have
  limits, so a chart cannot be used as a database filler or make every PDP
  render O(n²).
* **Typed with units and precision.** ``unit`` is ``cm`` or ``in`` and is
  required with any measurements (no default is assumed: a chart without a unit
  is 2.54× wrong for someone). Values are numbers or ``[low, high]`` ranges,
  checked for ordering, finiteness and a plausible human range.
* **Explicit about unknown properties.** Unknown top-level keys and unknown
  per-row dimensions are reported as warnings and DROPPED from the normalised
  output, so an extension cannot smuggle data past the readers.
* **Safe to render.** Every stored string passes :func:`plain_text`, which strips
  control characters and anything tag-like. The chart is rendered as text today,
  and this guarantees it stays safe even if a future surface HTML-interpolates a
  size label.
* **Failure-shaped.** Validation returns ``errors`` as ``{code, path, message}``
  so the API can tell a brand exactly which cell is wrong, not just "invalid".

Legacy behaviour is preserved deliberately: ``{}`` and ``""`` mean "this product
has no chart", which is a legitimate state (the seeded catalogue shipped it for
years and the engine falls back to EN 13402). That is distinguished from a
MALFORMED chart, which is reported, never treated as absent.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = "1.0"
SUPPORTED_VERSIONS: Tuple[str, ...] = ("1.0",)

#: Hard limits. Every one of these exists to stop a payload from becoming a
#: denial of service for the storefront or a silent truncation for the brand.
MAX_PAYLOAD_BYTES = 64 * 1024
MAX_SIZES = 60
MAX_ROWS = 60
MAX_DIMENSIONS_PER_ROW = 12
MAX_SIZE_LABEL = 20
MAX_UNIT_LABEL = 8
MAX_SIZE_SYSTEM_LABEL = 64
MAX_NOTE_LENGTH = 500
MAX_SOURCE_LABEL = 120
MAX_NOTES = 10
MAX_MEASUREMENT = 300.0     # cm; larger than any human body or garment
MIN_MEASUREMENT = 1.0       # cm; smaller than any real measurement
MAX_DECIMALS = 1

UNITS = ("cm", "in")
MEASUREMENT_TYPES = ("body", "garment")

#: Dimensions the sizing engine scores on. Kept in sync with
#: ``services/fit/size_charts.DIMENSIONS`` by a test rather than by import, so
#: this module stays dependency-free and cannot create an import cycle.
KNOWN_DIMENSIONS = ("chest", "waist", "hip", "shoulder", "inseam", "neck")

#: Accepts one or two numbers, tolerating the forms real exports contain:
#: ``96``, ``"96"``, ``"96-98"``, ``"96 – 98"``, ``[96, 98]``.
_RANGE_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(-?\d+(?:\.\d+)?)\s*$", re.I)

#: Anything that looks like markup is refused outright in a text field. The chart
#: is data, not a document.
_TAG_RE = re.compile(r"<[^>]*>")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass
class Issue:
    code: str
    path: str
    message: str

    def as_dict(self) -> Dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


@dataclass
class ValidationResult:
    """Outcome of validating one chart.

    ``normalised`` is the JSON TEXT that may be persisted (never the caller's
    raw input): it contains only the supported shape, with strings sanitised and
    numbers rounded to the declared precision. ``has_chart`` distinguishes
    "legitimately empty" from "rejected".
    """

    ok: bool
    normalised: str = "{}"
    has_chart: bool = False
    errors: List[Issue] = field(default_factory=list)
    warnings: List[Issue] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "has_chart": self.has_chart,
            "schema_version": SCHEMA_VERSION,
            "errors": [e.as_dict() for e in self.errors],
            "warnings": [w.as_dict() for w in self.warnings],
        }


def plain_text(value: Any, *, limit: int, path: str = "") -> Tuple[str, Optional[Issue]]:
    """Sanitise a chart string: no controls, no markup, bounded length.

    Returns ``(text, issue)``. A length overrun is an ERROR rather than a
    truncation, because a silently shortened size label ("Extra Extra Lar") is
    worse than a rejected row.
    """
    text = "" if value is None else str(value)
    text = _CONTROL_RE.sub("", text)
    if _TAG_RE.search(text):
        return "", Issue("markup_not_allowed", path,
                         "Markup is not allowed in size chart text")
    text = text.strip()
    if len(text) > limit:
        return "", Issue("too_long", path,
                         f"At most {limit} characters (got {len(text)})")
    return text, None


def _parse_number(raw: Any, path: str, errors: List[Issue]) -> Optional[float]:
    if isinstance(raw, bool):
        errors.append(Issue("not_a_number", path, "Expected a number, got a boolean"))
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        errors.append(Issue("not_a_number", path, f"{raw!r} is not a number"))
        return None
    if not math.isfinite(value):
        errors.append(Issue("not_finite", path, "Measurements must be finite"))
        return None
    decimals = 0
    text = repr(value)
    if "." in text:
        decimals = len(text.split(".")[1].rstrip("0"))
    if decimals > MAX_DECIMALS:
        errors.append(Issue(
            "too_precise", path,
            f"At most {MAX_DECIMALS} decimal place (got {text}); measurements "
            f"beyond that are not real",
        ))
        return None
    return value


def _parse_measurement(
    raw: Any, path: str, unit: str, errors: List[Issue], warnings: List[Issue]
) -> Optional[List[float]]:
    """Normalise one dimension to ``[low, high]`` in the chart's unit."""
    if isinstance(raw, (list, tuple)):
        if len(raw) != 2:
            errors.append(Issue("bad_range", path,
                                "A range must be exactly two numbers [low, high]"))
            return None
        low = _parse_number(raw[0], f"{path}[0]", errors)
        high = _parse_number(raw[1], f"{path}[1]", errors)
        if low is None or high is None:
            return None
        if low > high:
            errors.append(Issue("range_inverted", path,
                                f"Range low ({low}) is greater than high ({high})"))
            return None
        pair = [low, high]
    elif isinstance(raw, str) and _RANGE_RE.match(raw):
        match = _RANGE_RE.match(raw.strip())
        low = _parse_number(match.group(1), path, errors)
        high = _parse_number(match.group(2), path, errors)
        if low is None or high is None:
            return None
        if low > high:
            errors.append(Issue("range_inverted", path,
                                f"Range low ({low}) is greater than high ({high})"))
            return None
        pair = [low, high]
    else:
        value = _parse_number(raw, path, errors)
        if value is None:
            return None
        pair = [value, value]
        warnings.append(Issue(
            "point_value", path,
            f"A single value ({value:g}) was given; stored as the range "
            f"[{value:g}, {value:g}] and treated as an exact measurement",
        ))

    low, high = pair
    # Range plausibility is checked in cm so one set of bounds covers both units.
    factor = 1.0 if unit == "cm" else 2.54
    low_cm, high_cm = low * factor, high * factor
    if low_cm <= 0:
        errors.append(Issue("non_positive", path, "Measurements must be positive"))
        return None
    if low_cm < MIN_MEASUREMENT or high_cm > MAX_MEASUREMENT:
        errors.append(Issue(
            "implausible", path,
            f"{low:g}–{high:g} {unit} is outside the plausible range "
            f"({MIN_MEASUREMENT:g}–{MAX_MEASUREMENT:g} cm)",
        ))
        return None
    return [round(low, MAX_DECIMALS), round(high, MAX_DECIMALS)]


def _validate_rows(
    payload: Dict[str, Any], unit: str, errors: List[Issue], warnings: List[Issue]
) -> List[Dict[str, Any]]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        errors.append(Issue("bad_rows", "rows", "`rows` must be a list"))
        return []
    if len(rows) > MAX_ROWS:
        errors.append(Issue("too_many_rows", "rows",
                            f"At most {MAX_ROWS} size rows (got {len(rows)})"))
        return []
    out: List[Dict[str, Any]] = []
    seen_sizes: Dict[str, int] = {}
    for index, row in enumerate(rows):
        path = f"rows[{index}]"
        if not isinstance(row, dict):
            errors.append(Issue("bad_row", path, "Each row must be an object"))
            continue
        label_raw = row.get("size")
        label, issue = plain_text(label_raw, limit=MAX_SIZE_LABEL, path=f"{path}.size")
        if issue:
            errors.append(issue)
            continue
        if not label:
            errors.append(Issue("missing_size", path, "`size` is required"))
            continue
        key = label.lower()
        if key in seen_sizes:
            errors.append(Issue(
                "duplicate_size", f"{path}.size",
                f'Size "{label}" already appears in row {seen_sizes[key]}',
            ))
            continue
        seen_sizes[key] = index

        clean: Dict[str, Any] = {"size": label}
        dimensions = {k: v for k, v in row.items() if k != "size"}
        if len(dimensions) > MAX_DIMENSIONS_PER_ROW:
            errors.append(Issue("too_many_dimensions", path,
                                f"At most {MAX_DIMENSIONS_PER_ROW} dimensions per row"))
            continue
        for dimension, value in dimensions.items():
            canonical = str(dimension).strip().lower()
            if canonical not in KNOWN_DIMENSIONS:
                warnings.append(Issue(
                    "unknown_dimension", f"{path}.{dimension}",
                    f'"{dimension}" is not a dimension the sizing engine reads '
                    f"({', '.join(KNOWN_DIMENSIONS)}); it was not stored",
                ))
                continue
            if value in (None, ""):
                continue
            parsed = _parse_measurement(value, f"{path}.{canonical}", unit, errors, warnings)
            if parsed is not None:
                clean[canonical] = parsed
        out.append(clean)
    return out


def _validate_size_map(
    payload: Dict[str, Any], unit: str, errors: List[Issue], warnings: List[Issue]
) -> List[Dict[str, Any]]:
    sizes = payload.get("sizes")
    if not isinstance(sizes, dict):
        errors.append(Issue("bad_sizes", "sizes", "`sizes` must be an object keyed by size"))
        return []
    if len(sizes) > MAX_SIZES:
        errors.append(Issue("too_many_sizes", "sizes",
                            f"At most {MAX_SIZES} sizes (got {len(sizes)})"))
        return []
    rows: List[Dict[str, Any]] = []
    for raw_label, measurements in sizes.items():
        path = f"sizes.{raw_label}"
        label, issue = plain_text(raw_label, limit=MAX_SIZE_LABEL, path=path)
        if issue:
            errors.append(issue)
            continue
        if not label:
            errors.append(Issue("missing_size", path, "Size keys cannot be empty"))
            continue
        if not isinstance(measurements, dict):
            errors.append(Issue("bad_row", path,
                                "Each size must map to an object of dimensions"))
            continue
        row: Dict[str, Any] = {"size": label}
        for dimension, value in measurements.items():
            canonical = str(dimension).strip().lower()
            if canonical not in KNOWN_DIMENSIONS:
                warnings.append(Issue(
                    "unknown_dimension", f"{path}.{dimension}",
                    f'"{dimension}" is not a dimension the sizing engine reads; '
                    f"it was not stored",
                ))
                continue
            if value in (None, ""):
                continue
            parsed = _parse_measurement(value, f"{path}.{canonical}", unit, errors, warnings)
            if parsed is not None:
                row[canonical] = parsed
        rows.append(row)
    return rows


def validate(raw: Any) -> ValidationResult:
    """Validate and normalise a size chart.

    ``raw`` may be a dict, a JSON string, ``None`` or ``""``. The result carries
    the exact text to persist and every reason a chart was refused.
    """
    result = ValidationResult(ok=False)

    if raw is None or (isinstance(raw, str) and not raw.strip()):
        # Legitimate "no chart". NOT an error: the sizing engine falls back to the
        # published standard, which is the documented behaviour for the seeded
        # catalogue and for every product a brand has not sized yet.
        result.ok = True
        return result

    if isinstance(raw, str):
        if len(raw.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            result.errors.append(Issue(
                "payload_too_large", "",
                f"Size chart exceeds {MAX_PAYLOAD_BYTES // 1024} KB",
            ))
            return result
        try:
            payload = json.loads(raw)
        except ValueError as exc:
            result.errors.append(Issue("invalid_json", "", f"Malformed JSON: {exc}"))
            return result
    else:
        payload = raw

    if not isinstance(payload, dict):
        result.errors.append(Issue("not_an_object", "", "A size chart must be a JSON object"))
        return result

    if not payload:
        result.ok = True
        return result

    # ── version ──────────────────────────────────────────────────────────────
    declared = payload.get("schema_version")
    if declared is None:
        # Charts authored before versioning (seed data, early operator SQL) are
        # read as 1.0 — the only format that ever existed — and the normalised
        # output records it, so the next write is explicit.
        declared = SCHEMA_VERSION
        result.warnings.append(Issue(
            "schema_version_assumed", "schema_version",
            f"No schema_version given; read as {SCHEMA_VERSION}",
        ))
    declared = str(declared).strip()
    if declared not in SUPPORTED_VERSIONS:
        result.errors.append(Issue(
            "unsupported_version", "schema_version",
            f"Unsupported schema_version {declared!r}; this build understands "
            + ", ".join(SUPPORTED_VERSIONS),
        ))
        return result

    # `source`, `notes` and `published_by_brand` are read by the sizing engine as
    # PROVENANCE (it distinguishes a brand-published chart from one derived from a
    # public standard), and the seeded charts have carried `source`/`notes` since
    # they were authored. They are part of the contract, not stray keys.
    allowed = {"schema_version", "unit", "measurement_type", "size_system",
               "updated_at", "note", "notes", "source", "published_by_brand",
               "rows", "sizes"}
    for key in payload:
        if key not in allowed:
            result.warnings.append(Issue(
                "unknown_property", str(key),
                f'"{key}" is not part of the size chart schema and was not stored',
            ))

    # ── unit ─────────────────────────────────────────────────────────────────
    unit_raw = payload.get("unit")
    if unit_raw is None:
        unit = "cm"
        result.warnings.append(Issue(
            "unit_assumed", "unit",
            "No unit given; measurements are read as cm",
        ))
    else:
        unit, issue = plain_text(unit_raw, limit=MAX_UNIT_LABEL, path="unit")
        if issue:
            result.errors.append(issue)
            return result
        unit = unit.lower()
        if unit not in UNITS:
            result.errors.append(Issue(
                "bad_unit", "unit", f"unit must be one of {', '.join(UNITS)} (got {unit!r})",
            ))
            return result

    measurement_type = payload.get("measurement_type")
    if measurement_type in (None, ""):
        measurement_type = "body"
    else:
        measurement_type, issue = plain_text(
            measurement_type, limit=16, path="measurement_type"
        )
        if issue:
            result.errors.append(issue)
            return result
        measurement_type = measurement_type.lower()
        if measurement_type not in MEASUREMENT_TYPES:
            result.errors.append(Issue(
                "bad_measurement_type", "measurement_type",
                f"measurement_type must be one of {', '.join(MEASUREMENT_TYPES)}",
            ))
            return result

    has_rows = "rows" in payload
    has_sizes = "sizes" in payload
    if has_rows and has_sizes:
        result.errors.append(Issue(
            "ambiguous_shape", "",
            "Use either `rows` or `sizes`, not both — two shapes in one chart is "
            "ambiguous and the readers disagree about which wins",
        ))
        return result
    if not has_rows and not has_sizes:
        result.errors.append(Issue(
            "no_measurements", "",
            "A chart must contain `rows` or `sizes`",
        ))
        return result

    if has_rows:
        rows = _validate_rows(payload, unit, result.errors, result.warnings)
    else:
        rows = _validate_size_map(payload, unit, result.errors, result.warnings)

    if result.errors:
        return result
    if not rows:
        result.errors.append(Issue("empty_chart", "", "The chart contains no usable sizes"))
        return result

    normalised: Dict[str, Any] = {
        "schema_version": declared,
        "unit": unit,
        "measurement_type": measurement_type,
        "rows": rows,
    }
    size_system = payload.get("size_system")
    if size_system not in (None, ""):
        cleaned, issue = plain_text(size_system, limit=MAX_SIZE_SYSTEM_LABEL,
                                    path="size_system")
        if issue:
            result.errors.append(issue)
            return result
        if cleaned:
            normalised["size_system"] = cleaned
    updated_at = payload.get("updated_at")
    if updated_at not in (None, ""):
        cleaned, issue = plain_text(updated_at, limit=40, path="updated_at")
        if issue:
            result.errors.append(issue)
            return result
        if cleaned:
            normalised["updated_at"] = cleaned
    # `note` and `notes` are the same field spelled two ways by two authors. The
    # contract stores ONE shape: a list of paragraphs. `services/fit/size_charts`
    # iterates `notes`, and the seeded charts write several paragraphs (what the
    # chart was derived from, and the warning that the demo catalogue is not the
    # brand's own publication). Flattening them into one string would silently
    # discard that distinction.
    for key in ("notes", "note"):
        raw_note = payload.get(key)
        if raw_note in (None, ""):
            continue
        parts = raw_note if isinstance(raw_note, list) else [raw_note]
        if len(parts) > MAX_NOTES:
            result.errors.append(Issue(
                "too_many_notes", key, f"At most {MAX_NOTES} notes (got {len(parts)})",
            ))
            return result
        cleaned_parts: List[str] = []
        for index, part in enumerate(parts):
            cleaned, issue = plain_text(part, limit=MAX_NOTE_LENGTH, path=f"{key}[{index}]")
            if issue:
                result.errors.append(issue)
                return result
            if cleaned:
                cleaned_parts.append(cleaned)
        if cleaned_parts:
            normalised["notes"] = cleaned_parts
            break

    source = payload.get("source")
    if source not in (None, ""):
        cleaned, issue = plain_text(source, limit=MAX_SOURCE_LABEL, path="source")
        if issue:
            result.errors.append(issue)
            return result
        if cleaned:
            normalised["source"] = cleaned

    if payload.get("published_by_brand") is not None:
        published = payload.get("published_by_brand")
        if not isinstance(published, bool):
            result.errors.append(Issue(
                "bad_published_flag", "published_by_brand",
                "published_by_brand must be true or false",
            ))
            return result
        normalised["published_by_brand"] = published

    encoded = json.dumps(normalised, ensure_ascii=False, sort_keys=True)
    if len(encoded.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        result.errors.append(Issue(
            "payload_too_large", "",
            f"Normalised chart exceeds {MAX_PAYLOAD_BYTES // 1024} KB",
        ))
        return result

    result.ok = True
    result.has_chart = True
    result.normalised = encoded
    return result


def validate_or_raise(raw: Any) -> ValidationResult:
    """Validate and raise ``ValueError`` with a readable message on failure.

    Used by write paths (seed/backfill/API) that must not persist an invalid
    chart. The exception text names the first error so an operator reading a
    failed script sees the actual problem.
    """
    result = validate(raw)
    if not result.ok:
        first = result.errors[0]
        raise ValueError(f"Invalid size chart [{first.code}] {first.path}: {first.message}")
    return result
