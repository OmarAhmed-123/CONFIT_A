"""Offline plumbing tests for the VTON benchmark harness.

No GPU, no network, no heavy deps. They prove the harness runs and, crucially, that
it REFUSES to fabricate a result: a dry run yields no renders and no quality scores.
"""

from pathlib import Path

import pytest

from adapters import DryRunAdapter, FashnSegfeeLocalAdapter, HostedApiAdapter
from harness.manifest import ManifestError, consent_gaps, diversity_summary, load_manifest
from harness.rubric import load_rubric, score
from harness.runner import run

HERE = Path(__file__).resolve().parents[1]
EXAMPLE = HERE / "datasets" / "manifest.example.json"
RUBRIC = HERE / "rubric.json"


def test_example_manifest_loads_and_is_diverse():
    data = load_manifest(EXAMPLE)
    assert len(data["cases"]) >= 3
    div = diversity_summary(data)
    assert div["category"]  # categories present
    assert any(c.get("modest_wear") for c in data["cases"]), "set must include modest wear"


def test_manifest_rejects_bad_cases(tmp_path):
    bad = tmp_path / "m.json"
    bad.write_text('{"cases": [{"id": "a", "person_image": "p", "garment_image": "g", "category": "hats"}]}', encoding="utf-8")
    with pytest.raises(ManifestError):
        load_manifest(bad)
    dup = tmp_path / "d.json"
    dup.write_text('{"cases": [{"id":"a","person_image":"p","garment_image":"g","category":"tops"},{"id":"a","person_image":"p","garment_image":"g","category":"tops"}]}', encoding="utf-8")
    with pytest.raises(ManifestError):
        load_manifest(dup)


def test_dryrun_adapter_never_renders():
    r = DryRunAdapter().render({"id": "x", "category": "tops"}, "/tmp", 1234)
    assert r.is_render is False and "DRY RUN" in (r.error or "")


def test_real_adapters_are_gated_by_default():
    gpu_ok, _ = FashnSegfeeLocalAdapter().available()
    paid_ok, _ = HostedApiAdapter("fashn_api", "FASHN_API_KEY").available()
    assert gpu_ok is False and paid_ok is False


def test_runner_dry_run_produces_no_renders():
    data = load_manifest(EXAMPLE)
    result = run([DryRunAdapter(), FashnSegfeeLocalAdapter()], data, "/tmp", dry_run=True)
    assert result["summary"]["renders"] == 0
    assert all(r["is_render"] is False for r in result["results"])


def test_scorer_refuses_to_score_non_renders():
    data = load_manifest(EXAMPLE)
    rubric = load_rubric(RUBRIC)
    result = run([DryRunAdapter()], data, "/tmp", dry_run=True)
    from adapters.base import RenderResult
    results = [RenderResult(**{k: v for k, v in r.items()}) for r in result["results"]]
    verdict = score(rubric, results, case_scores={})
    assert verdict["scored"] is False
    assert "refusing" in verdict["reason"]


def test_rubric_has_the_hard_fail_dimensions():
    rubric = load_rubric(RUBRIC)
    keys = {d["key"] for d in rubric["quality_dimensions"]}
    assert {"garment_fidelity", "identity_preservation", "modest_wear_fit"} <= keys
    modest = next(d for d in rubric["quality_dimensions"] if d["key"] == "modest_wear_fit")
    assert "hard_fail_below" in modest


def test_consent_gaps_detects_missing():
    data = {"cases": [{"id": "a", "consent_status": ""}, {"id": "b", "consent_status": "ok"}]}
    assert consent_gaps(data) == ["a"]
