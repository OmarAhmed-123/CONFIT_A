"""Central semantic metadata for analytics metrics (2026-09-24 re-audit).

The N/A-honesty work (PR #189) made zero-denominator rates publish ``null``
instead of a fabricated ``0.0``. What was still missing, and what this module
owns, is the MACHINE-READABLE distinction a consumer needs to render those
numbers responsibly:

* ``measured``      — the denominator existed; the value is real (0.0 is a
                      real, measured zero — not absence of data).
* ``unmeasured_zero_denominator`` — nobody was in the cohort; the value is
                      ``None`` and must be rendered as N/A, never as 0.
* sample sizes ride WITH the value, so "97% (n=3)" can never be presented
  with the confidence of "97% (n=30,000)".

Minimum-sample suppression is deliberately NOT implemented here:

* the k-anonymity floor for heatmaps already exists and stays where it is
  (``HEATMAP_MIN_SAMPLE`` — a PRIVACY threshold, a different concern);
* a *statistical* minimum sample for publishing cohort comparisons is a
  business/product decision that has not been made. Inventing "30" in a
  repository file would be exactly the kind of fabricated rigour the audit
  exists to remove. ``MIN_SAMPLE_POLICY`` states that openly on the wire.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

STATUS_MEASURED = "measured"
STATUS_UNMEASURED = "unmeasured_zero_denominator"

# Published verbatim by the analytics endpoints. threshold=None is a fact,
# not a placeholder: no suppression threshold has been decided.
MIN_SAMPLE_POLICY: Dict[str, Any] = {
    "threshold": None,
    "status": "pending_business_decision",
    "note": (
        "No minimum-sample suppression is applied to cohort comparisons yet: "
        "the threshold is a business decision that has not been made. Until "
        "it is, every metric carries its sample size so consumers can judge "
        "significance themselves. (Privacy k-anonymity for heatmaps is a "
        "separate, already-enforced control.)"
    ),
}


def measured_metric(value: Optional[float], sample_size: int) -> Dict[str, Any]:
    """Wrap a rate/percentage with its measurement status and sample size.

    ``value is None`` with a positive sample size is a contract violation by
    the caller (a measured cohort must produce a number), so status derives
    from the sample size alone — the single source of truth.
    """
    if sample_size > 0:
        return {
            "value": value,
            "status": STATUS_MEASURED,
            "sample_size": int(sample_size),
        }
    return {
        "value": None,
        "status": STATUS_UNMEASURED,
        "sample_size": 0,
    }
