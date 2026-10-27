"""Repeatable recommendation-quality evaluation for the wardrobe stylist.

Runs the documented scenario set (docs/qa/eval/wardrobe_stylist_eval_dataset.json)
through the REAL endpoint ``POST /api/v1/wardrobe/outfit-recommendation`` in-process
(FastAPI TestClient, throwaway SQLite) and scores every answer.

Modes
  --mode deterministic   rule-based baseline (WARDROBE_STYLIST_PROVIDER=deterministic); free
  --mode live            real watsonx.ai inference with the configured reasoning model
                         (WARDROBE_STYLIST_PROVIDER=watsonx, strict: no silent fallback).
                         Needs WATSONX_APIKEY / WATSONX_PROJECT_ID / WATSONX_URL in the env.
                         Costs tokens — the run is bounded by the dataset (16 + repeats).

What is scored automatically
  HARD FAILURES (counted, never averaged away)
    H1 model referenced an id outside the wardrobe   (rejected_references > 0)
    H2 duplicate item in the outfit
    H3 banned colour present
    H4 incomplete outfit although the wardrobe was completable
    H5 wrong response language (Arabic requested but prose not Arabic, or vice-versa)
    H6 provenance mismatch (source / ai_generated / model_id vs the mode)
    H7 invalid response (non-200 / unparseable)
    H8 image_url not the one stored for that wardrobe id
    H9 role contradiction (dress together with top/bottom)
  HEURISTIC RUBRIC 1-5 (automatic, documented in docs/qa/WARDROBE_STYLIST_QUALITY_REPORT.md)
    constraint_compliance, inventory_fidelity, completeness, seasonal_appropriateness,
    colour_coordination, pattern_discipline, explanation_quality, occasion_fit
  SUBJECTIVE rubric rows (garment compatibility, visual coherence, overall usefulness)
    are left for a reviewer; the JSON has empty slots for them.

Raw model output is captured by wrapping WatsonxClient.chat (tee), per scenario, so the
report can show exactly what the model said before validation. Nothing is persisted by
the application itself (by design); the capture lives only in the report JSON.

Usage
  PYTHONPATH=. python scripts/eval/wardrobe_stylist_quality_eval.py --mode deterministic
  set -a && source ~/.env.local && set +a && \
  PYTHONPATH=. python scripts/eval/wardrobe_stylist_quality_eval.py --mode live
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "docs/qa/eval/wardrobe_stylist_eval_dataset.json"
OUT_DIR = ROOT / "docs/qa/eval"

ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
NEUTRALS = {"Black", "White", "Ivory", "Grey", "Navy", "Beige", "Tan", "Brown"}
SEASON_WORDS = {"summer": "Summer", "winter": "Winter", "spring": "Spring", "autumn": "Autumn"}


def _bootstrap(mode: str) -> None:
    """Environment must be set BEFORE importing the app (settings are read at import)."""
    db = f"/tmp/wardrobe_eval_{uuid.uuid4().hex[:8]}.db"
    os.environ["ENVIRONMENT"] = "test"
    os.environ["DATABASE_URL"] = f"sqlite:///{db}"
    os.environ.pop("ALEMBIC_DATABASE_URL", None)
    os.environ["WARDROBE_VISION_PROVIDER"] = "deterministic"
    if mode == "deterministic":
        os.environ["WARDROBE_STYLIST_PROVIDER"] = "deterministic"
    else:
        os.environ["WARDROBE_STYLIST_PROVIDER"] = "watsonx"
        for k in ("WATSONX_APIKEY", "WATSONX_PROJECT_ID", "WATSONX_URL"):
            if not os.environ.get(k):
                sys.exit(f"--mode live needs {k} in the environment (load ~/.env.local). Not running.")


def _arabic_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if ARABIC_RE.match(c)) / len(letters)


class Capture:
    """Tee of WatsonxClient.chat: raw content, served model, latency, attempts."""

    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    def install(self):
        from backend.app.providers.watsonx import client as mod
        orig_chat = mod.WatsonxClient.chat
        orig_once = mod.WatsonxClient._chat_once
        cap = self

        async def chat(self_, **kw):
            rec = {"attempts": 0, "started": time.perf_counter()}
            cap.calls.append(rec)
            try:
                res = await orig_chat(self_, **kw)
                rec.update({"raw_content": res.content, "served_model_id": res.model_id,
                            "usage": res.usage, "finish_reason": res.finish_reason, "ok": True})
                return res
            except Exception as exc:
                rec.update({"ok": False, "error": type(exc).__name__ + ": " + str(exc)[:200]})
                raise
            finally:
                rec["latency_s"] = round(time.perf_counter() - rec.pop("started"), 3)

        async def once(self_, *a, **kw):
            if cap.calls:
                cap.calls[-1]["attempts"] += 1
            return await orig_once(self_, *a, **kw)

        mod.WatsonxClient.chat = chat
        mod.WatsonxClient._chat_once = once

    def take(self) -> list[dict[str, Any]]:
        out, self.calls = self.calls, []
        return out


def _score(scn: dict[str, Any], req: dict[str, Any], resp: dict[str, Any] | None,
           status: int, created: dict[int, dict[str, Any]], mode: str, model_id: str,
           banned: set, normalize_color) -> dict[str, Any]:
    hard: list[str] = []
    rubric: dict[str, int | None] = {}
    exp = scn["expect"]
    if status != 200 or not isinstance(resp, dict):
        hard.append("H7_invalid_response")
        return {"hard_failures": hard, "rubric": rubric}

    items = resp.get("items") or []
    ids = [i["wardrobe_item_id"] for i in items]
    roles = [i["role"] for i in items]
    fams = [normalize_color(i.get("color_name")) for i in items]

    if resp.get("rejected_references"):
        hard.append("H1_model_referenced_unknown_id")
    if len(set(ids)) != len(ids):
        hard.append("H2_duplicate_item")
    if banned and any(f in banned for f in fams):
        hard.append("H3_banned_colour_present")
    if exp.get("completable") and not resp.get("is_complete"):
        hard.append("H4_incomplete_when_completable")
    prose = " ".join([resp.get("title") or "", resp.get("summary") or ""] + [i.get("reason") or "" for i in items])
    ar = _arabic_ratio(prose)
    if exp.get("language") == "ar" and ar < 0.5:
        hard.append("H5_wrong_language")
    if exp.get("language") == "en" and ar > 0.2:
        hard.append("H5_wrong_language")
    if mode == "live":
        if resp.get("source") != "watsonx" or resp.get("ai_generated") is not True or resp.get("model_id") != model_id:
            hard.append("H6_provenance_mismatch")
    else:
        if resp.get("source") != "deterministic_fallback" or resp.get("ai_generated") is not False:
            hard.append("H6_provenance_mismatch")
    for i in items:
        row = created.get(i["wardrobe_item_id"])
        if row is None or (i.get("image_url") or "") != row["image_url"]:
            hard.append("H8_image_item_mismatch")
            break
    if "dress" in roles and ({"top", "bottom"} & set(roles)):
        hard.append("H9_role_contradiction")

    # ── heuristic rubric ─────────────────────────────────────────────
    rubric["constraint_compliance"] = 1 if "H3_banned_colour_present" in hard else 5
    rubric["inventory_fidelity"] = 1 if ("H1_model_referenced_unknown_id" in hard or "H8_image_item_mismatch" in hard) else 5
    if exp.get("completable"):
        rubric["completeness"] = 5 if resp.get("is_complete") else 2
    else:
        # honest incompleteness: missing_categories must name the gap
        miss = set(resp.get("missing_categories") or [])
        want = set(exp.get("missing_expected") or [])
        rubric["completeness"] = 5 if (want <= miss and not resp.get("is_complete")) or exp.get("conflict_expected") else 2

    season = SEASON_WORDS.get((req.get("season") or "").lower())
    if season:
        mism = 0
        for i in items:
            row = created.get(i["wardrobe_item_id"]) or {}
            s = row.get("seasonality", "All-Season")
            if s not in ("All-Season", season):
                mism += 1
        rubric["seasonal_appropriateness"] = max(1, 5 - 2 * mism)
    else:
        rubric["seasonal_appropriateness"] = None

    distinct = set(fams)
    accents = distinct - NEUTRALS
    if len(distinct) <= 3 and len(accents) <= 1:
        rubric["colour_coordination"] = 5
    elif len(distinct) <= 4 and len(accents) <= 2:
        rubric["colour_coordination"] = 3
    else:
        rubric["colour_coordination"] = 2
    if items and len(distinct) <= 3 and len(accents) == 1 and "Multi" not in distinct:
        pass

    core = [i for i in items if i["role"] in ("top", "bottom", "dress", "footwear")]
    patterned = sum(1 for i in core if (created.get(i["wardrobe_item_id"]) or {}).get("pattern", "Solid") not in ("Solid", "Textured", "Denim Wash"))
    rubric["pattern_discipline"] = 5 if patterned <= 1 else (3 if patterned == 2 else 2)

    ctx_tokens = [t.lower() for t in [req.get("occasion", ""), req.get("season") or "", req.get("time_of_day") or "",
                                       req.get("location") or "", req.get("activity") or ""] if t]
    reasons = [i.get("reason") or "" for i in items]
    generic = sum(1 for r in reasons if r.startswith("Selected for a") or "rule-based" in r.lower() or len(r) < 25)
    mentions = sum(1 for r in reasons if any(tok and tok.split()[0] in r.lower() for tok in ctx_tokens))
    if resp.get("source") == "deterministic_fallback":
        # template reasons are generic by construction; never above 3
        rubric["explanation_quality"] = 3 if reasons else 1
    elif not reasons:
        rubric["explanation_quality"] = 1
    elif generic == 0 and mentions >= max(1, len(reasons) // 2):
        rubric["explanation_quality"] = 5
    elif generic == 0:
        rubric["explanation_quality"] = 4
    elif generic < len(reasons):
        rubric["explanation_quality"] = 3
    else:
        rubric["explanation_quality"] = 2

    occ = req.get("occasion", "").lower()
    fit_hits = 0
    for i in items:
        occs = [o.lower() for o in (created.get(i["wardrobe_item_id"]) or {}).get("occasions", [])]
        if any(occ in o or o in occ for o in occs):
            fit_hits += 1
    if exp.get("unsuitable_inventory"):
        # nothing in the wardrobe fits; honesty is what counts — a limitation or
        # assumption that mentions the occasion/activity, not the generic fallback notice
        notes = " ".join((resp.get("limitations") or []) + (resp.get("assumptions") or []) + [resp.get("summary") or ""]).lower()
        words = [w for w in (occ.split() + (req.get("activity") or "").lower().split()) if len(w) > 3]
        rubric["occasion_fit"] = 4 if any(w in notes for w in words) else 2
    elif items:
        frac = fit_hits / len(items)
        rubric["occasion_fit"] = 5 if frac >= 0.99 else (4 if frac >= 0.66 else (3 if frac >= 0.34 else 2))
    else:
        rubric["occasion_fit"] = 1

    rubric["garment_compatibility_REVIEWER"] = None
    rubric["visual_coherence_REVIEWER"] = None
    rubric["overall_usefulness_REVIEWER"] = None
    return {"hard_failures": hard, "rubric": rubric}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["deterministic", "live"], required=True)
    ap.add_argument("--only", help="comma-separated scenario ids")
    ap.add_argument("--no-repeats", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args()
    _bootstrap(args.mode)

    from fastapi.testclient import TestClient

    from backend.app.core.config import settings
    from backend.app.main import app
    from backend.app.providers.watsonx.prompts import STYLIST_PROMPT_VERSION
    from backend.app.schemas.wardrobe_stylist import OutfitRecommendationRequest
    from backend.app.services.wardrobe_stylist_service import WardrobeStylistService
    from backend.app.services.wardrobe_taxonomy import normalize_color

    app.state.limiter.enabled = False  # one user runs every scenario; limits are tested elsewhere
    cap = Capture()
    if args.mode == "live":
        cap.install()
    model_id = settings.WATSONX_REASONING_MODEL_ID
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    scenarios = data["scenarios"]
    if args.only:
        keep = set(args.only.split(","))
        scenarios = [s for s in scenarios if s["id"] in keep]

    results: list[dict[str, Any]] = []
    with TestClient(app) as client:
        email = f"eval_{uuid.uuid4().hex[:8]}@confit.io"
        r = client.post("/api/v1/auth/register", json={"email": email, "password": "Password123!", "full_name": "Eval User"})
        assert r.status_code == 201, r.text
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        def run(scn: dict[str, Any], repeat: int = 0) -> dict[str, Any]:
            # fresh wardrobe per run: bin whatever is there
            for it in (client.get("/api/v1/wardrobe/items", headers=headers).json() or []):
                client.delete(f"/api/v1/wardrobe/items/{it['id']}", headers=headers)
            created: dict[int, dict[str, Any]] = {}
            for title, cat, color, pattern, occasions, season in scn["wardrobe"]:
                payload = {
                    "title": title, "category": cat, "subcategory": title, "color_name": color,
                    "color_hex": "#777777", "pattern": pattern, "occasions": occasions, "seasonality": season,
                    "image_url": f"https://cdn.example.com/eval/{uuid.uuid4().hex}.jpg",
                }
                res = client.post("/api/v1/wardrobe/items", json=payload, headers=headers)
                assert res.status_code == 201, res.text
                row = res.json()
                created[row["id"]] = {"title": title, "category": cat, "color": color, "pattern": pattern,
                                      "occasions": occasions, "seasonality": season, "image_url": row["image_url"]}
            req = dict(scn["request"])
            banned = WardrobeStylistService.banned_color_families(OutfitRecommendationRequest(**req))
            t0 = time.perf_counter()
            res = client.post("/api/v1/wardrobe/outfit-recommendation", json=req, headers=headers)
            latency = round(time.perf_counter() - t0, 3)
            body = res.json() if res.headers.get("content-type", "").startswith("application/json") else None
            scored = _score(scn, req, body, res.status_code, created, args.mode, model_id, banned, normalize_color)
            calls = cap.take() if args.mode == "live" else []
            return {
                "scenario_id": scn["id"], "repeat": repeat, "request": req, "expect": scn["expect"],
                "wardrobe": created, "http_status": res.status_code, "latency_s": latency,
                "model_calls": calls,
                "response": body if res.status_code == 200 else (body or res.text[:400]),
                "final_items": [{"id": i["wardrobe_item_id"], "role": i["role"], "title": i["title"],
                                 "color": i["color_name"], "reason": i["reason"]} for i in (body or {}).get("items", [])] if res.status_code == 200 else [],
                **scored,
            }

        for scn in scenarios:
            out = run(scn)
            results.append(out)
            print(f"{scn['id']:<48} {out['http_status']} {out['latency_s']:>6.2f}s items={len(out['final_items'])} hard={out['hard_failures']}")

        consistency: dict[str, Any] = {}
        rep = data.get("consistency_repeats") or {}
        if rep and not args.no_repeats and not args.only:
            by_id = {s["id"]: s for s in scenarios}
            for sid in rep["scenario_ids"]:
                runs = [next(r_ for r_ in results if r_["scenario_id"] == sid)]
                for k in range(1, rep["runs"]):
                    runs.append(run(by_id[sid], repeat=k))
                    results.append(runs[-1])
                sets = [frozenset(i["title"] for i in r_["final_items"]) for r_ in runs]
                jac = []
                for a in range(len(sets)):
                    for b in range(a + 1, len(sets)):
                        u = sets[a] | sets[b]
                        jac.append(len(sets[a] & sets[b]) / len(u) if u else 1.0)
                consistency[sid] = {"runs": len(runs), "item_sets": [sorted(s) for s in sets],
                                    "mean_pairwise_jaccard": round(statistics.mean(jac), 3) if jac else None,
                                    "hard_failures_per_run": [r_["hard_failures"] for r_ in runs]}
                print(f"consistency {sid}: jaccard={consistency[sid]['mean_pairwise_jaccard']}")

    # ── aggregate ────────────────────────────────────────────────────
    base = [r_ for r_ in results if r_["repeat"] == 0]
    n = len(base)
    hard_counts: dict[str, int] = {}
    for r_ in base:
        for h in r_["hard_failures"]:
            hard_counts[h] = hard_counts.get(h, 0) + 1
    rubric_keys = [k for k in base[0]["rubric"] if not k.endswith("_REVIEWER")] if base else []
    rubric_means = {}
    for k in rubric_keys:
        vals = [r_["rubric"][k] for r_ in base if r_["rubric"].get(k) is not None]
        rubric_means[k] = round(statistics.mean(vals), 2) if vals else None
    lat = [r_["latency_s"] for r_ in results if r_["http_status"] == 200]
    calls = [c for r_ in results for c in r_["model_calls"]]
    summary = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": args.mode,
        "model_id_configured": model_id if args.mode == "live" else None,
        "served_model_ids": sorted({c.get("served_model_id") for c in calls if c.get("served_model_id")}),
        "prompt_version": STYLIST_PROMPT_VERSION,
        "dataset_version": data["version"],
        "scenarios": n, "total_runs": len(results),
        "scenarios_with_any_hard_failure": sum(1 for r_ in base if r_["hard_failures"]),
        "hard_failure_counts": hard_counts,
        "hard_constraint_violation_rate": round(sum(1 for r_ in base if any(h.startswith(("H3", "H9")) for h in r_["hard_failures"])) / n, 3) if n else None,
        "inventory_hallucination_rate": round(sum(1 for r_ in base if any(h.startswith(("H1", "H8")) for h in r_["hard_failures"])) / n, 3) if n else None,
        "model_failure_rate": round(sum(1 for r_ in base if "H7_invalid_response" in r_["hard_failures"]) / n, 3) if n else None,
        "rubric_means_1to5": rubric_means,
        "latency_s": {"p50": round(statistics.median(lat), 3) if lat else None,
                      "max": max(lat) if lat else None, "mean": round(statistics.mean(lat), 3) if lat else None},
        "model_call_attempts_total": sum(c.get("attempts", 0) for c in calls),
        "model_calls_total": len(calls),
        "consistency": consistency,
        "reviewer_scores": "NOT COLLECTED — *_REVIEWER rubric rows are empty; see the quality report for how they are filled",
    }
    out_path = Path(args.out) if args.out else OUT_DIR / f"wardrobe_stylist_eval_{args.mode}_{datetime.now(UTC).strftime('%Y%m%d')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print("written", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
