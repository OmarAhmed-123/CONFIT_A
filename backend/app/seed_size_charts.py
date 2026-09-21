"""Seed size charts for the demo catalogue.

Why this file exists
--------------------
Every seeded product shipped with ``size_chart_json = "{}"``. The sizing engine
(``services/fit/*``) therefore never had a brand chart to read and fell back to
the EN 13402-3 standard table for *everything*, which made the provenance card
in the UI say "standard fallback" on all nine products. That is honest but it
left the brand-chart code path — the one the audit specifically flagged as
unverified — unexercised outside of tests.

What the numbers are
--------------------
These are **not** scraped from the real brands. CONFIT_A's catalogue is a demo
catalogue with invented products, so inventing a matching chart would be the
same fabrication the audit is about. Instead each chart is derived from a
citable public source and says so in its own ``source``/``notes`` fields, which
the engine surfaces verbatim to the user:

* Letter-sized garments use the **EN 13402-3** letter-code girth table
  (men's chest / women's bust), the same public standard the engine falls back
  to — but attached to the product with an explicit derivation note, and with
  the ease and secondary dimensions adjusted per garment class.
* Numeric jacket sizes (38/40) use the standard UK/US jacket convention where
  the number **is** the chest girth in inches.
* Numeric trouser sizes (30/32/34) use the convention where the number is the
  waist girth in inches.
* Dress sizes 6/8 use the UK dress-size bust/waist/hip progression.
* Footwear and accessories get **no chart at all**. Shoe length and "One Size"
  clutches are not body-girth problems, and the engine must refuse rather than
  pretend. Leaving them empty is the point: it keeps a live example of the
  refusal path in the seeded data.

Any product not listed here keeps ``{}`` and falls back to the standard.
"""

from __future__ import annotations

import json
from typing import Any, Dict

# Charts are authored in the units the source states, and the parser converts.
# ``updated_at`` is the date the chart content was last reviewed, not the date
# the row was inserted — the UI shows it so a stale chart is visible as stale.
_REVIEWED = "2026-09-21"

_EN13402_NOTE = (
    "Derived from EN 13402-3 letter-code girth ranges (men's chest / women's bust). "
    "Demo catalogue: this is a standards-derived chart, not a chart published by the brand."
)


def _rows(*rows: Dict[str, Any]) -> list:
    return list(rows)


SIZE_CHARTS_BY_SLUG: Dict[str, Dict[str, Any]] = {
    # ---------------------------------------------------------------- tops
    "relaxed-organic-poplin-oxford-shirt": {
        "unit": "cm",
        "measurement_type": "body",
        "size_system": "EN 13402-3 letter",
        "updated_at": _REVIEWED,
        "source": "EN 13402-3 (men's chest girth letter codes)",
        "notes": [_EN13402_NOTE, "Cut relaxed: the body ranges below assume a generous chest ease."],
        "rows": _rows(
            {"size": "S", "chest": [86, 94], "waist": [72, 80], "neck": [37, 38]},
            {"size": "M", "chest": [94, 102], "waist": [80, 88], "neck": [39, 40]},
            {"size": "L", "chest": [102, 110], "waist": [88, 96], "neck": [41, 42]},
        ),
    },
    # ----------------------------------------------------------- outerwear
    "tailored-italian-wool-double-breasted-blazer": {
        "unit": "cm",
        "measurement_type": "body",
        "size_system": "EN 13402-3 letter",
        "updated_at": _REVIEWED,
        "source": "EN 13402-3 (men's chest girth letter codes)",
        "notes": [
            _EN13402_NOTE,
            "Double-breasted and structured: sized to the body chest, with a shoulder "
            "dimension because a blazer cannot be let out across the shoulder.",
        ],
        "rows": _rows(
            {"size": "S", "chest": [86, 94], "waist": [72, 80], "shoulder": [42.0, 44.0]},
            {"size": "M", "chest": [94, 102], "waist": [80, 88], "shoulder": [44.0, 46.0]},
            {"size": "L", "chest": [102, 110], "waist": [88, 96], "shoulder": [46.0, 48.0]},
            {"size": "XL", "chest": [110, 118], "waist": [96, 104], "shoulder": [48.0, 50.0]},
        ),
    },
    "tuxedo-peak-lapel-evening-dinner-jacket": {
        "unit": "in",
        "measurement_type": "body",
        "size_system": "UK/US jacket (chest inches)",
        "updated_at": _REVIEWED,
        "source": "UK/US tailoring convention: the jacket number is the body chest girth in inches",
        "notes": [
            "A '40' jacket is drafted for a 40 inch body chest; the maker adds the ease.",
            "Demo catalogue: convention-derived, not published by the brand.",
        ],
        "rows": _rows(
            {"size": "38", "chest": "37-39", "waist": "31-33"},
            {"size": "40", "chest": "39-41", "waist": "33-35"},
        ),
    },
    # -------------------------------------------------------------- bottoms
    "pleated-tapered-virgin-wool-trousers": {
        "unit": "in",
        "measurement_type": "body",
        "size_system": "US waist (inches)",
        "updated_at": _REVIEWED,
        "source": "US/UK trouser convention: the size number is the body waist girth in inches",
        "notes": [
            "Pleated and tapered: sized off the natural waist, with a seat/hip range "
            "because a taper fails at the hip before it fails at the waist.",
            "Demo catalogue: convention-derived, not published by the brand.",
        ],
        "rows": _rows(
            {"size": "30", "waist": "29.5-30.5", "hip": "37-39", "inseam": "31-32"},
            {"size": "32", "waist": "31.5-32.5", "hip": "39-41", "inseam": "31-32"},
            {"size": "34", "waist": "33.5-34.5", "hip": "41-43", "inseam": "31-32"},
        ),
    },
    # -------------------------------------------------------------- dresses
    "silk-slip-column-maxi-dress": {
        "unit": "cm",
        "measurement_type": "body",
        "size_system": "UK dress",
        "updated_at": _REVIEWED,
        "source": "UK dress-size bust/waist/hip progression (4 cm steps), cross-checked against EN 13402-3 women's bust codes",
        "notes": [
            "A bias-cut silk column has almost no ease anywhere: the hip range is the "
            "binding dimension, not the bust.",
            "Demo catalogue: standards-derived, not published by the brand.",
        ],
        "rows": _rows(
            {"size": "6", "bust": [78, 82], "waist": [60, 64], "hip": [86, 90]},
            {"size": "8", "bust": [82, 86], "waist": [64, 68], "hip": [90, 94]},
        ),
    },
    # Footwear and accessories intentionally omitted — see the module docstring.
}


def size_chart_json_for_slug(slug: str) -> str:
    """Return the JSON string for a product slug, or ``"{}"`` when none applies.

    ``"{}"`` is a meaningful value, not a placeholder: the engine reads it as
    "this brand publishes no chart" and either falls back to the public
    standard or refuses, and it says which in the response.
    """
    chart = SIZE_CHARTS_BY_SLUG.get(slug)
    return json.dumps(chart, ensure_ascii=False) if chart else "{}"
