"""Load the acceptance rubric and score a candidate against it.

The rubric encodes the thresholds in docs/tryon/00-research-plan.md §3. Scoring
REFUSES to produce quality numbers unless every result is a real render — a dry
run or a gated adapter yields no score, by design.
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean, pstdev
from typing import Iterable

from adapters.base import RenderResult


def load_rubric(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def score(rubric: dict, results: Iterable[RenderResult], case_scores: dict[str, dict[str, float]]) -> dict:
    """``case_scores``: {case_id: {dimension_key: 1..5}} from human/second-reviewer
    grading. Returns a verdict; ``scored`` is False when any result is not a real
    render (so a dry run can never masquerade as a passing benchmark)."""
    results = list(results)
    non_renders = sorted({r.case_id for r in results if not r.is_render})
    if non_renders:
        return {
            "scored": False,
            "reason": "non-render results present (dry run or gated adapter); refusing to emit quality scores",
            "non_renders": non_renders,
        }

    verdict: dict = {"scored": True, "passed": True, "dimensions": {}, "hard_fails": [], "policy": rubric.get("policy")}
    for dim in rubric.get("quality_dimensions", []):
        key = dim["key"]
        if "min_mean" not in dim:
            continue  # non-mean dimensions (e.g. robustness) scored separately
        vals = [case_scores[cid][key] for cid in case_scores if key in case_scores.get(cid, {})]
        if not vals:
            verdict["dimensions"][key] = {"status": "no_scores"}
            verdict["passed"] = False
            continue
        m = mean(vals)
        sd = pstdev(vals) if len(vals) > 1 else 0.0
        ok = m >= dim["min_mean"]
        hf_below = dim.get("hard_fail_below")
        hard = (
            [cid for cid in case_scores if case_scores[cid].get(key, 5) < hf_below]
            if hf_below is not None else []
        )
        if hard:
            verdict["hard_fails"].append({"dimension": key, "cases": sorted(hard), "note": dim.get("hard_fail_note")})
            ok = False
        verdict["dimensions"][key] = {"mean": round(m, 3), "stdev": round(sd, 3), "min_mean": dim["min_mean"], "pass": ok}
        if not ok:
            verdict["passed"] = False
    verdict["n_cases_scored"] = len(case_scores)
    return verdict
