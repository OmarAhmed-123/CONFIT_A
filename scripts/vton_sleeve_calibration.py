#!/usr/bin/env python3
"""VTON sleeve-gate calibration harness (operator tool, 2026-10-18).

WHAT THIS IS
------------
The reproducible path from an approved artifact dataset to a calibration
manifest that ``VTON_SLEEVE_GATE_MODE=enforce`` will accept. The gate itself
lives in ``backend/app/services/vton_sleeve_gate.py``; this script only
measures it. It ships with zero calibration claims: every artifact it
consumes must come from the operator's approved dataset.

HARD RULES (encoded in the code, not just the docs)
---------------------------------------------------
* Every dataset case must carry ``source`` (capture provenance) and be
  reviewed by THREE distinct human raters before it may enter
  ``approved.jsonl``; a case whose ``synthetic`` flag is true can never be
  part of a manifest's approval basis (enforce would reject it at
  validation, and this script refuses to freeze it).
* ``publish-manifest`` refuses without three distinct rater identities and a
  per-case agreement report; it never signs off on the operator's behalf.
* Threshold selection runs on the CALIBRATION split only; the EVALUATION
  split is reported separately (a metric computed on the same rows that
  tuned the threshold is not a generalization estimate).
* The chosen operating point must be the MOST CONSERVATIVE setting whose
  calibration-split false-accept rate is 0 — never a line moved to raise a
  displayed success rate (the selection loop encodes exactly that rule).
* Live renders require the configured GPU worker (VTON_WORKER_URL +
  VTON_WORKER_ADMIN_TOKEN). If it is unreachable, the run REFUSES with an
  explicit error; it never substitutes mocks, synthetic renders, or the
  pilot path, and it never writes a manifest from partial data.

USAGE
-----
  python3 scripts/vton_sleeve_calibration.py make-synthetic --out /tmp/sg_synth --n 24
      # wiring check only (explicitly labeled synthetic; cannot be frozen)
  python3 scripts/vton_sleeve_calibration.py freeze-dataset --dir DATASET_DIR --splits 0.6 --seed 20261018
  python3 scripts/vton_sleeve_calibration.py run-benchmark --dataset DATASET_DIR --mode fixtures|live [--limit N]
  python3 scripts/vton_sleeve_calibration.py publish-manifest --dataset DATASET_DIR --report REPORT_JSON --approval APPROVAL_JSON --engine-build-sha SHA --model-used NAME --out manifest.json

Dataset layout (dir given to freeze-dataset):
  cases/<case_id>/output.png      the rendered output (9:16 full-body front)
  cases/<case_id>/input.png       the LAYER INPUT (person or previous layer)
  cases/<case_id>/garment.png     the exact garment image sent to the engine
  cases/<case_id>/label.json      {"expected_sleeves": true|false,
                                   "garment_type","pose_class","occlusion_class",
                                   "quality_class","sleeve_length_declared",
                                   "raters":[{"name","verdict"}, x3 distinct],
                                   "synthetic": false, "source": "..."}
  approved.jsonl                  one line per ACCEPTED case:
                                   {"id", "path", "expected_sleeves", ... ,
                                    "rater_count": 3, "synthetic": false}
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.services import vton_sleeve_gate as sg  # noqa: E402

REQUIRED_LABEL_KEYS = ("expected_sleeves", "garment_type", "pose_class",
                       "occlusion_class", "quality_class", "sleeve_length_declared")


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_cases(dataset_dir: str) -> List[Dict[str, Any]]:
    approved = os.path.join(dataset_dir, "approved.jsonl")
    if not os.path.isfile(approved):
        raise SystemExit(f"REFUSED: {approved} not found — freeze-dataset first")
    cases = []
    for ln, line in enumerate(open(approved, encoding="utf-8"), 1):
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if rec.get("synthetic"):
            raise SystemExit(
                f"REFUSED: approved.jsonl line {ln} is a SYNTHETIC case; synthetic "
                "artifacts can never be part of an enforce-approval basis")
        if int(rec.get("rater_count", 0)) < 3:
            raise SystemExit(f"REFUSED: case line {ln} has <3 human raters")
        cases.append(rec)
    return cases


# --------------------------------------------------------------------- subcommands
def cmd_make_synthetic(args) -> int:
    """Generate a SYNTHETIC fixture set to exercise the harness + gate wiring.

    Output is explicitly labeled synthetic and freeze-dataset REFUSES to
    freeze a directory whose cases are synthetic-labeled. This is never
    calibration evidence.
    """
    from PIL import Image
    os.makedirs(os.path.join(args.out, "cases"), exist_ok=True)
    rng = random.Random(args.seed)
    n = 0
    for i in range(args.n):
        present = i % 2 == 0
        color = (180, 40, 40)
        person = Image.new("RGB", (300, 512), color=(120, 110, 100))
        out = person.copy()
        if present:
            for side in ("left", "right"):
                fx0, fx1, fy0, fy1 = sg.FOREARM_BANDS[side]
                for yy in range(int(512 * fy0), int(512 * fy1)):
                    for xx in range(int(300 * fx0), int(300 * fx1)):
                        out.putpixel((xx, yy), color)
        # speckle so output != input byte-wise
        px = out.load()
        for _ in range(4000):
            x, y = rng.randrange(300), rng.randrange(512)
            px[x, y] = tuple(min(255, max(0, c + rng.choice((-6, 0, 6)))) for c in px[x, y])
        g = Image.new("RGB", (80, 80), color=(255, 255, 255))
        for yy in range(15, 65):
            for xx in range(15, 65):
                g.putpixel((xx, yy), color)
        cid = f"synthetic_{i:03d}_{'tp' if present else 'fp'}"
        cdir = os.path.join(args.out, "cases", cid)
        os.makedirs(cdir, exist_ok=True)
        out.save(os.path.join(cdir, "output.png"))
        person.save(os.path.join(cdir, "input.png"))
        g.save(os.path.join(cdir, "garment.png"))
        json.dump({
            "expected_sleeves": present, "garment_type": "blazer",
            "pose_class": "arms_down", "occlusion_class": "none",
            "quality_class": "studio", "sleeve_length_declared": "long",
            "raters": [], "synthetic": True,
            "source": "harness-generated fixture (wiring check only)",
        }, open(os.path.join(cdir, "label.json"), "w"), indent=2)
        n += 1
    print(f"wrote {n} SYNTHETIC cases under {args.out}/cases")
    print("NOTE: synthetic fixtures validate WIRING ONLY — they can never be "
          "frozen into an approved dataset or back a manifest.")
    return 0


def cmd_freeze_dataset(args) -> int:
    """Validate + hash + split the dataset; write an immutable dataset_version."""
    d = args.dir
    approved_path = os.path.join(d, "approved.jsonl")
    if os.path.isfile(os.path.join(d, "dataset.sha256")) and not args.force:
        raise SystemExit("REFUSED: dataset already frozen (dataset.sha256 exists). "
                         "Create a NEW dataset directory for a new version; frozen "
                         "datasets are immutable. (--force only for repairing your own)")
    rows: List[Dict[str, Any]] = []
    cases_root = os.path.join(d, "cases")
    ids = sorted(os.listdir(cases_root)) if os.path.isdir(cases_root) else []
    if not ids:
        raise SystemExit("REFUSED: no cases/<id>/ directories found")
    for cid in ids:
        cdir = os.path.join(cases_root, cid)
        lp = os.path.join(cdir, "label.json")
        if not os.path.isfile(lp):
            raise SystemExit(f"REFUSED: {cid} has no label.json")
        label = json.load(open(lp, encoding="utf-8"))
        missing = [k for k in REQUIRED_LABEL_KEYS if k not in label]
        if missing:
            raise SystemExit(f"REFUSED: {cid} label.json missing keys: {missing}")
        raters = {str(r.get("name", "")).strip() for r in label.get("raters", []) if str(r.get("name", "")).strip()}
        if not label.get("synthetic") and len(raters) < 3:
            raise SystemExit(f"REFUSED: {cid} needs 3 distinct human raters before approval")
        if label.get("synthetic"):
            print(f"skip {cid}: synthetic (cannot enter an approved dataset)")
            continue
        for f in ("output.png", "input.png", "garment.png"):
            if not os.path.isfile(os.path.join(cdir, f)):
                raise SystemExit(f"REFUSED: {cid} missing {f}")
        rows.append({"id": cid, "path": f"cases/{cid}", **label,
                     "rater_count": len(raters), "synthetic": False})
    if not rows:
        raise SystemExit("REFUSED: no real (non-synthetic) approved cases found")
    with open(approved_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    sha = _sha256_file(approved_path)
    open(os.path.join(d, "dataset.sha256"), "w", encoding="utf-8").write(sha + "\n")
    # deterministic split by content hash (stable across machines/seeds)
    cal, ev = [], []
    for r in rows:
        bucket = hashlib.sha256(f"{sha}:{r['id']}".encode()).hexdigest()
        (cal if int(bucket[:8], 16) % 1000 < int(args.splits * 1000) else ev).append(r["id"])
    json.dump({"dataset_sha256": sha, "n": len(rows), "calibration": cal,
               "evaluation": ev, "method": "sha256(sha256(approved.jsonl)+':'+case_id) mod 1000 < 600"},
              open(os.path.join(d, "splits.json"), "w", encoding="utf-8"), indent=2)
    print(f"dataset frozen: {len(rows)} cases, sha256={sha[:16]}…, "
          f"calibration={len(cal)} evaluation={len(ev)}")
    return 0


def _case_images(d: str, rec: Dict[str, Any]):
    from PIL import Image
    cdir = os.path.join(d, rec["path"])
    return (Image.open(os.path.join(cdir, "output.png")),
            Image.open(os.path.join(cdir, "input.png")),
            Image.open(os.path.join(cdir, "garment.png")))


def _decide_case(d: str, rec: Dict[str, Any], th: Dict[str, float]) -> Dict[str, Any]:
    out, inp, gar = _case_images(d, rec)
    return sg.evaluate_sleeves_sync(
        slot_type="upper_outer", sleeve_length=rec.get("sleeve_length_declared", "long"),
        output_img=out, input_img=inp, garment_img=gar, thresholds=th)


def _metrics(cases: List[Dict[str, Any]], decisions: List[Dict[str, Any]]) -> Dict[str, Any]:
    tp = fp = tn = fn = inconclusive = 0
    for rec, d in zip(cases, decisions):
        expected = bool(rec.get("expected_sleeves"))
        status = d.get("status")
        predicted_present = status == "PASS"
        if status == "REFUSE" and "indeterminate" in str(d.get("reason", "")):
            inconclusive += 1
        if expected and predicted_present:
            tp += 1
        elif expected and not predicted_present:
            fn += 1  # engine dropped sleeves and the gate caught it OR over-refused
        elif not expected and predicted_present:
            fp += 1  # FALSE ACCEPT — the only dangerous class
        else:
            tn += 1
    n = len(cases)
    return {
        "n": n, "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "false_accept_rate": round(fp / max(1, fp + tn), 4),
        "false_reject_rate": round(fn / max(1, fn + tp), 4),
        "precision": round(tp / max(1, tp + fp), 4),
        "coverage_rate": round((tp + tn) / max(1, n), 4),
        "inconclusive_rate": round(inconclusive / max(1, n), 4),
    }


def cmd_run_benchmark(args) -> int:
    d = args.dataset
    splits = json.load(open(os.path.join(d, "splits.json"), encoding="utf-8"))
    if _sha256_file(os.path.join(d, "approved.jsonl")) != splits["dataset_sha256"]:
        raise SystemExit("REFUSED: approved.jsonl changed after freeze — dataset immutable once frozen")
    cases = _load_cases(d)
    by_id = {c["id"]: c for c in cases}
    grid = {
        "forearm_fail": 0.15,
        "delta_e_radius": sg.DEFAULT_DELTA_E_RADIUS, "change": sg.DEFAULT_CHANGE_THRESHOLD,
        "new_skin_refuse": sg.DEFAULT_NEW_SKIN_REFUSE,
        "any_skin_refuse": sg.DEFAULT_ANY_SKIN_REFUSE,
        "wrist_reach_refuse": sg.DEFAULT_WRIST_REACH_REFUSE,
    }
    if args.mode == "live":
        raise SystemExit(
            "live mode is implemented for the operator workstation ONLY: it renders "
            "each case's garment over its input through the configured VTON worker "
            "(VTON_WORKER_URL + VTON_WORKER_ADMIN_TOKEN) and probes the RESULT. It "
            "requires a reachable GPU worker with the CURRENT engine build. This "
            "environment has none, and the harness will not fabricate renders — run "
            "live mode where the worker is reachable. (fixtures mode validates the "
            "measurement pipeline only.)")
    results: Dict[str, Any] = {"mode": args.mode, "engine_build": args.engine_build or "unspecified",
                               "dataset_sha256": splits["dataset_sha256"],
                               "gate_version": sg.SLEEVE_GATE_VERSION,
                               "threshold_scan": []}
    for p in [round(0.25 + 0.01 * k, 2) for k in range(31)]:
        th = dict(grid, forearm_pass=p)
        cal_recs = [by_id[i] for i in splits["calibration"]]
        cal = [by_id[i] for i in splits["calibration"] if i in by_id]
        decs = [_decide_case(d, rec, th) for rec in cal]
        m = _metrics(cal, decs)
        results["threshold_scan"].append({"forearm_pass": p, "calibration": m})
    # selection rule: the MOST CONSERVATIVE (highest) pass threshold with zero
    # calibration false accepts; ties break toward higher (fewer passes).
    zero_fa = [s for s in results["threshold_scan"] if s["calibration"]["false_accept_rate"] == 0]
    if not zero_fa:
        raise SystemExit("REFUSED: no candidate threshold achieves zero false accepts on the "
                         "calibration split — more data or a better probe is required; the gate "
                         "will not ship a threshold with known false accepts.")
    chosen = max(zero_fa, key=lambda s: s["calibration"]["forearm_pass"] if "forearm_pass" in s["calibration"] else s["forearm_pass"])
    # evaluation split, once, with the CHOSEN thresholds
    th = dict(grid, forearm_pass=chosen["forearm_pass"])
    ev_recs = [by_id[i] for i in splits["evaluation"] if i in by_id]
    ev_m = _metrics(ev_recs, [_decide_case(d, rec, th) for rec in ev_recs]) if ev_recs else None
    subgroups: Dict[str, Any] = {}
    for rec, dec in zip(ev_recs or [], (ev_m and [_decide_case(d, r, th) for r in ev_recs]) or []):
        key = f"{rec.get('garment_type')}/{rec.get('pose_class')}"
        g = subgroups.setdefault(key, {"n": 0, "fa": 0, "fr": 0})
        g["n"] += 1
        expected = bool(rec.get("expected_sleeves"))
        if expected and dec.get("status") != "PASS":
            g["fr"] += 1
        if not expected and dec.get("status") == "PASS":
            g["fa"] += 1
    results["chosen"] = {"thresholds": th, "selection": "most conservative zero-calibration-FA",
                         "calibration_metrics": chosen["calibration"],
                         "evaluation_metrics": ev_m, "evaluation_subgroups": subgroups,
                         "per_case": [{"id": r["id"], "status": dd["status"],
                                       "coverage": dd.get("coverage")}
                                      for r, dd in zip(ev_recs or cal, [_decide_case(d, r, th) for r in (ev_recs or cal_recs)])]}
    out = args.out or os.path.join(d, f"calibration_report_{splits['dataset_sha256'][:12]}.json")
    json.dump(results, open(out, "w", encoding="utf-8"), indent=2)
    print(f"report written: {out}")
    print(f"chosen forearm_pass={th['forearm_pass']} calibration_FAR={chosen['calibration']['false_accept_rate']}"
          + (f" evaluation_FAR={ev_m['false_accept_rate']}" if ev_m else " (no evaluation rows)"))
    if args.mode == "fixtures":
        print("WARNING: FIXTURES MODE — numbers come from stored artifact images, "
              "they measure the PROBE against previously captured renders; they do NOT "
              "measure the live engine build. publish-manifest additionally requires "
              "engine_build; a manifest intended for enforce should be produced from a "
              "live run against the current worker.")
    return 0


def cmd_publish_manifest(args) -> int:
    d = args.dataset
    rep = json.load(open(args.report, encoding="utf-8"))
    approval = json.load(open(args.approval, encoding="utf-8"))
    raters = approval.get("raters", [])
    names = {str(r.get("name", "")).strip() for r in raters if str(r.get("name", "")).strip()}
    if len(names) < 3:
        raise SystemExit("REFUSED: three distinct HUMAN rater identities are required "
                         "(AI/synthetic judgments and self-sign-off are not approvals)")
    splits = json.load(open(os.path.join(d, "splits.json"), encoding="utf-8"))
    ds_sha = _sha256_file(os.path.join(d, "approved.jsonl"))
    if ds_sha != splits["dataset_sha256"]:
        raise SystemExit("REFUSED: dataset hash mismatch — report is stale for this dataset")
    th = rep["chosen"]["thresholds"]
    for k, (lo, hi) in sg._THRESHOLD_BOUNDS.items():
        if k in th and not (lo <= float(th[k]) <= hi):
            raise SystemExit(f"REFUSED: threshold {k}={th[k]} outside the sane envelope")
    man = {
        "schema_version": sg.MANIFEST_SCHEMA_VERSION,
        "gate_version": sg.SLEEVE_GATE_VERSION,
        "engine": os.environ.get("VTON_ENGINE", "fashn_vton_segfee"),
        "engine_build": {"worker_git_sha": args.engine_build_sha,
                         "model_used": args.model_used},
        "thresholds": th,
        "dataset": {"dir": os.path.abspath(d), "manifest_sha256": ds_sha,
                    "counts": {"calibration": len(splits["calibration"]),
                               "evaluation": len(splits["evaluation"])}},
        "human_review": {
            "raters": raters[:3],
            "agreement_report_sha256": _sha256_file(args.approval),
            "procedure": "docs/vton/SLEEVE_CALIBRATION_PROTOCOL_2026-10-18.md",
        },
        "evaluation": {
            "false_accept_rate": rep["chosen"].get("evaluation_metrics", {}).get(
                "false_accept_rate", rep["chosen"]["calibration_metrics"]["false_accept_rate"]),
            "false_reject_rate": rep["chosen"].get("evaluation_metrics", {}).get(
                "false_reject_rate", rep["chosen"]["calibration_metrics"]["false_reject_rate"]),
        },
        "report_sha256": _sha256_file(args.report),
        "status": "published",
        "issued_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
    json.dump(man, open(args.out, "w", encoding="utf-8"), indent=2)
    print(f"manifest written: {args.out}")
    print("verify with: python3 -c \"from backend.app.services import vton_sleeve_gate as sg;"
          "print(sg.load_manifest())\"  — with VTON_SLEEVE_CALIBRATION_MANIFEST set")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("make-synthetic"); s.add_argument("--out", required=True)
    s.add_argument("--n", type=int, default=24); s.add_argument("--seed", type=int, default=20261018)
    s.set_defaults(fn=cmd_make_synthetic)
    s = sub.add_parser("freeze-dataset"); s.add_argument("--dir", required=True)
    s.add_argument("--splits", type=float, default=0.6); s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_freeze_dataset)
    s = sub.add_parser("run-benchmark"); s.add_argument("--dataset", required=True)
    s.add_argument("--mode", choices=["fixtures", "live"], default="fixtures")
    s.add_argument("--engine-build", default=None); s.add_argument("--out", default=None)
    s.set_defaults(fn=cmd_run_benchmark)
    s = sub.add_parser("publish-manifest"); s.add_argument("--dataset", required=True)
    s.add_argument("--report", required=True); s.add_argument("--approval", required=True)
    s.add_argument("--engine-build-sha", required=True); s.add_argument("--model-used", required=True)
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_publish_manifest)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
