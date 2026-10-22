"""Load and validate a benchmark dataset manifest.

The manifest is the single source of truth for the test set: which image pairs are
run, their category, and — critically — their provenance and consent status. No
image bytes are committed to the repo; the manifest references local files that an
operator populates from a consented, diverse source (see datasets/README.md).
"""

from __future__ import annotations

import json
from pathlib import Path

REQUIRED_FIELDS = ("id", "person_image", "garment_image", "category")
# Recommended descriptors so the set can be shown to be diverse and the results
# sliced by body type / skin tone / difficulty / modest wear.
RECOMMENDED_FIELDS = (
    "body_type", "skin_tone", "pose", "lighting", "difficulty",
    "modest_wear", "source", "consent_status", "license",
)
VALID_CATEGORIES = ("tops", "bottoms", "one-pieces")


class ManifestError(ValueError):
    """Raised when a manifest is structurally invalid."""


def load_manifest(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ManifestError("manifest must contain a non-empty 'cases' list")
    seen: set[str] = set()
    for i, case in enumerate(cases):
        for field in REQUIRED_FIELDS:
            if field not in case:
                raise ManifestError(f"cases[{i}] is missing required field {field!r}")
        cid = case["id"]
        if cid in seen:
            raise ManifestError(f"duplicate case id {cid!r}")
        seen.add(cid)
        if case["category"] not in VALID_CATEGORIES:
            raise ManifestError(
                f"case {cid!r}: category {case['category']!r} must be one of {VALID_CATEGORIES}"
            )
    return data


def consent_gaps(data: dict) -> list[str]:
    """Case ids with no documented consent_status. A run over real people's
    photos should refuse to proceed while this is non-empty (operator policy)."""
    return [c["id"] for c in data["cases"] if not str(c.get("consent_status") or "").strip()]


def diversity_summary(data: dict) -> dict:
    """Counts per descriptor, so a set that is not actually diverse is visible."""
    out: dict[str, dict[str, int]] = {}
    for key in ("category", "body_type", "skin_tone", "difficulty", "modest_wear"):
        counts: dict[str, int] = {}
        for c in data["cases"]:
            v = str(c.get(key, "unspecified"))
            counts[v] = counts.get(v, 0) + 1
        out[key] = counts
    return out
