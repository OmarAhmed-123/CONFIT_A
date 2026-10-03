"""Feature 06 — LIVE type-aware evaluation against the deployed worker.

TATTOO (arXiv:2509.23242) is pinned as feature 06's evaluation rubric: a
compatibility model earns its place only if type-consistent outfits
actually score above type-inconsistent ones, and a completion model only
if it ranks the right completion first. Those properties CANNOT be tested
locally (the 2×769MB fp32 checkpoints exceed any CI host) — they are
asserted HERE, against the real deployed `confit-outfit-worker`, running
the exact pinned weights (sha256s in vendor provenance).

Run (after `modal deploy services/outfit-worker`):
  OUTFIT_WORKER_COMPAT_URL=<url> OUTFIT_WORKER_FITB_URL=<url> \
  OUTFIT_WORKER_ADMIN_TOKEN=<token> \
    python3 -m pytest tests/test_deployed_type_aware_eval.py -v

Each Modal web endpoint has its own stable URL (endpoint labels
"compatibility" / "fill-in-the-blank" / "health"); the health URL is
derived from the compat URL by suffix swap unless OUTFIT_WORKER_HEALTH_URL
is set explicitly.

Skipped (not failed) when the env vars are absent, so the pure-logic suite
stays green offline.
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"

COMPAT_URL = os.environ.get("OUTFIT_WORKER_COMPAT_URL", "").rstrip("/")
FITB_URL = os.environ.get("OUTFIT_WORKER_FITB_URL", "").rstrip("/")
TOKEN = os.environ.get("OUTFIT_WORKER_ADMIN_TOKEN", "")


def _health_url() -> str:
    explicit = os.environ.get("OUTFIT_WORKER_HEALTH_URL", "").rstrip("/")
    if explicit:
        return explicit
    # label-stable sibling: .../confit-outfit-worker-compatibility.modal.run
    # -> .../confit-outfit-worker-health.modal.run
    return COMPAT_URL.replace("-compatibility", "-health")


pytestmark = pytest.mark.skipif(
    not COMPAT_URL or not FITB_URL or not TOKEN,
    reason="OUTFIT_WORKER_COMPAT_URL / OUTFIT_WORKER_FITB_URL / "
           "OUTFIT_WORKER_ADMIN_TOKEN not set — live evaluation runs only "
           "against the deployed worker.",
)


def _data_url(name: str) -> str:
    blob = (FIXTURES / name).read_bytes()
    return "data:image/jpeg;base64," + base64.b64encode(blob).decode()


def _post(url: str, payload: dict, token: str = TOKEN):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-VTON-Admin": token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=280) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
        except Exception:
            body = {}
        # FastAPI wraps worker errors as {"detail": {"error": {...}}} —
        # unwrap for the caller so assertions read body["error"] directly.
        if isinstance(body.get("detail"), dict) and "error" in body["detail"]:
            body = body["detail"]
        return e.code, body


def _get(url: str):
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {}


def _item(name: str, slot: str, title: str) -> dict:
    return {"image_base64_or_url": _data_url(name), "slot": slot, "title": title}


# TATTOO fixtures: type-consistent vs type-inconsistent with REAL photos.
FORMAL_OUTFIT = [
    _item("blazer_navy.jpg", "upper_outer", "navy wool blazer"),
    _item("wool_trousers.jpg", "lower", "grey wool trousers"),
    _item("leather_oxford_shoes.jpg", "footwear", "brown leather oxford shoes"),
]
CLASH_OUTFIT = [
    _item("blazer_navy.jpg", "upper_outer", "navy wool blazer"),
    _item("silk_maxi_dress.jpg", "full_body", "silk maxi dress"),
    _item("leather_oxford_shoes.jpg", "footwear", "brown leather oxford shoes"),
]


class TestHealth:
    def test_health_reports_engine_and_licenses(self):
        status, body = _get(_health_url())
        assert status == 200
        assert body["status"] == "healthy"
        assert body["engine"] == "outfit_transformer_clip_cpu"
        assert body["models_loaded"] is True
        assert body["device"] == "cpu"
        assert body["commercial"] is True

    def test_readiness_ok(self):
        status, body = _get(_health_url().replace("-health", "-readiness"))
        assert status == 200 and body["ready"] is True


class TestAuthBoundary:
    def test_missing_token_is_401(self):
        status, body = _post(COMPAT_URL, {"job_id": "t", "items": FORMAL_OUTFIT[:2]}, token="")
        assert status == 401
        assert body["error"]["code"] == "UNAUTHORIZED"

    def test_wrong_token_is_401(self):
        status, body = _post(COMPAT_URL, {"job_id": "t", "items": FORMAL_OUTFIT[:2]}, token="wrong")
        assert status == 401


class TestCompatibilityTypeAwareEval:
    """The TATTOO-rubric core assertion: type-consistent > type-inconsistent."""

    def test_formal_outfit_outscores_type_clashing_outfit(self):
        status, formal = _post(COMPAT_URL, {
            "job_id": "eval-formal", "items": FORMAL_OUTFIT})
        assert status == 200, formal
        assert formal["status"] == "ok"
        assert formal["engine"] == "outfit_transformer_clip_cpu"

        status, clash = _post(COMPAT_URL, {
            "job_id": "eval-clash", "items": CLASH_OUTFIT})
        assert status == 200, clash

        f = formal["compatibility_score"]
        c = clash["compatibility_score"]
        # The blazer+trousers+oxfords look is a coherent type-consistent
        # outfit; blazer OVER a silk maxi dress with the same shoes is a
        # type clash (full-body + full upper/lower stack). The trained
        # model must separate them — if it cannot, it adds no value over
        # the heuristic engine and must not ship.
        assert f > c, (
            f"type-aware eval FAILED: coherent={f} clash={c} — "
            "the model does not separate type-consistent outfits"
        )

    def test_response_contract_is_honest(self):
        status, body = _post(COMPAT_URL, {
            "job_id": "eval-contract", "items": FORMAL_OUTFIT})
        assert status == 200
        assert 0.0 <= body["compatibility_score"] <= 1.0
        assert body["compatibility_score_0_100"] == int(
            round(body["compatibility_score"] * 100))
        assert body["items_count"] == 3
        assert body["models"]["outfit_transformer"]["license"] == "mit"
        assert body["models"]["fashionclip"]["bias_note"]
        assert "Polyvore" in body["training_data_note"]
        # type-aware block present and structurally honest
        ta = body["type_aware"]
        assert ta["polyvore_categories"] == ["outerwear", "bottoms", "shoes"]
        assert ta["coverage"]["missing_essentials"] == ["upper_inner"]
        assert ta["duplicate_slots"] == []
        # TATTOO-style axes present, advisory and labeled
        axes = body["aesthetic_axes"]
        assert axes["method"] == "clip_text_anchor_projection"
        assert set(axes["axes"]) >= {"color", "style", "season", "occasion",
                                     "material", "balance"}
        assert axes["overall"] is not None

    def test_single_item_refused(self):
        status, body = _post(COMPAT_URL, {
            "job_id": "eval-one", "items": FORMAL_OUTFIT[:1]})
        assert status == 422
        assert body["error"]["code"] == "INVALID_OUTFIT"

    def test_duplicate_slot_flagged_in_type_aware_block(self):
        status, body = _post(COMPAT_URL, {
            "job_id": "eval-dup",
            "items": [
                _item("blazer_navy.jpg", "upper_outer", "navy blazer"),
                _item("blazer_navy.jpg", "upper_outer", "second blazer"),
                _item("wool_trousers.jpg", "lower", "trousers"),
            ]})
        assert status == 200
        assert body["type_aware"]["duplicate_slots"] == ["upper_outer"]


class TestFillInTheBlankTypeAwareEval:
    def test_ranks_correct_completion_first(self):
        # Partial formal outfit; the footwear slot is blank. Candidates:
        # the type-correct completion (oxford shoes) vs a type-clashing
        # one (a silk maxi dress). CIR must rank the oxford first.
        status, body = _post(FITB_URL, {
            "job_id": "eval-fitb",
            "outfit": FORMAL_OUTFIT[:2],   # blazer + trousers
            "candidates": [
                {"id": "201", "image_base64_or_url": _data_url("silk_maxi_dress.jpg"),
                 "slot": "full_body", "title": "silk maxi dress"},
                {"id": "101", "image_base64_or_url": _data_url("leather_oxford_shoes.jpg"),
                 "slot": "footwear", "title": "brown leather oxford shoes"},
            ],
            "target_slot": "footwear",
            "top_k": 2,
        })
        assert status == 200, body
        ranked = body["ranked"]
        assert len(ranked) == 2
        assert ranked[0]["id"] == "101"
        assert ranked[0]["rank"] == 1
        assert ranked[0]["similarity"] > ranked[1]["similarity"]
        assert body["target_category_used"] == "shoes"

    def test_no_candidates_refused(self):
        status, body = _post(FITB_URL, {
            "job_id": "eval-fitb-none", "outfit": FORMAL_OUTFIT[:2],
            "candidates": [], "target_slot": "footwear"})
        assert status == 422
        assert body["error"]["code"] == "NO_CANDIDATES"
