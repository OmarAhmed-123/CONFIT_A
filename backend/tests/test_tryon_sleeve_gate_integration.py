"""Sleeve-gate integration: the REAL ``_call_gpu_worker`` choke point + the
sync multi-render contract, driven by a fake httpx worker (zero GPU).

Proves the mode semantics end-to-end through production code paths:
  off      — no gate runs, worker wire payload carries NO gate-only metadata;
  observe  — verdicts are measured + attached, a render is NEVER blocked;
  enforce  — REFUSE fails the request with the canonical
             VTON_SLEEVES_NOT_VERIFIED code and no image is delivered;
             and enforce without a valid calibration manifest refuses the
             render even when the image looks perfect (never a fallback to
             defaults, never a pass).

Mocked ENGINE — these tests validate gate wiring/decision flow only; they
are NOT calibration evidence (no real renders, no human raters).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import random
import uuid

import pytest
from PIL import Image
from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.services import vton_sleeve_gate as sg
from backend.app.services.tryon_service import TryOnService

UNIQUE = uuid.uuid4().hex[:8]

GRAY = (120, 110, 100)
RED = (180, 40, 40)


def _speckled(color, seed: int, w=300, h=512) -> str:
    rng = random.Random(seed)
    img = Image.new("RGB", (w, h), color=color)
    px = img.load()
    for _ in range(20000):  # byte-distinct but color-stable: defeats the echo
        x, y = rng.randrange(w), rng.randrange(h)
        px[x, y] = tuple(min(255, max(0, c + rng.choice((-6, -3, 0, 3, 6)))) for c in color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _garment_b64(color) -> str:
    img = Image.new("RGB", (80, 80), color=(255, 255, 255))
    px = img.load()
    for yy in range(15, 65):
        for xx in range(15, 65):
            px[xx, yy] = color
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


class _Resp:
    def __init__(self, code, payload):
        self.status_code = code
        self.text = ""
        self._p = payload

    def json(self):
        return self._p


class _GateClient:
    """Fake worker: returns configured solid-ish colors per call; captures the
    wire payload so the garment-metadata stripping can be asserted."""
    out_colors: list = []
    captured: list = []
    _n = 0

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, *a, **k):
        return _Resp(200, {"ready": True})

    async def post(self, *a, **k):
        _GateClient._n += 1
        payload = k.get("json") or {}
        _GateClient.captured.append(payload)
        i = min(_GateClient._n - 1, len(_GateClient.out_colors) - 1)
        return _Resp(200, {
            "rendered_image_data_url": _GateClient.out_colors[i],
            "model_used": "segfee-testmodel (http-mocked)",
            "fit_verdict": "n/a",
            "layers_processed": 1,
            "execution_time_ms": 12,
            "verify": {"PASS": True, "metric_pixel_change": 40.0,
                       "metric_color_shift": 0.05, "metric_image_stddev": 40.0},
        })


@pytest.fixture
def fake_worker(monkeypatch):
    _GateClient.out_colors = []
    _GateClient.captured = []
    _GateClient._n = 0
    monkeypatch.setenv("VTON_WORKER_URL", "https://worker.invalid/process")
    monkeypatch.setattr("httpx.AsyncClient", _GateClient)
    return _GateClient


def _write_valid_manifest(tmp_path, monkeypatch) -> None:
    ds = tmp_path / "dataset"
    ds.mkdir()
    approved = ds / "approved.jsonl"
    approved.write_text(json.dumps({"id": "fixture", "synthetic": True}) + "\n", encoding="utf-8")
    man = {
        "schema_version": sg.MANIFEST_SCHEMA_VERSION,
        "gate_version": sg.SLEEVE_GATE_VERSION,
        "engine": (settings.VTON_ENGINE or "fashn_vton_segfee"),
        "engine_build": {"worker_git_sha": "c" * 40, "model_used": "segfee-testmodel"},
        "thresholds": dict(sg.active_thresholds(None)),
        "dataset": {"dir": str(ds),
                    "manifest_sha256": hashlib.sha256(approved.read_bytes()).hexdigest()},
        "human_review": {
            "raters": [{"name": "A. Rater"}, {"name": "B. Rater"}, {"name": "C. Rater"}],
            "agreement_report_sha256": "d" * 64,
        },
        "evaluation": {"false_accept_rate": 0.0, "false_reject_rate": 0.05},
    }
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(man), encoding="utf-8")
    monkeypatch.setattr(settings, "VTON_SLEEVE_CALIBRATION_MANIFEST", str(p), raising=False)


def _set_mode(monkeypatch, mode):
    monkeypatch.setattr(settings, "VTON_SLEEVE_GATE_MODE", mode, raising=False)


def _run(svc, person, garments):
    return asyncio.run(svc._call_gpu_worker(
        job_id=f"sgtest_{UNIQUE}", person_image=person, garments=garments,
        gender_mode="male", output_aspect="9:16"))


def _g(pid, slot, sleeve, color=RED):
    return {"product_id": pid, "slot_type": slot,
            "image_base64": _garment_b64(color), "sleeve_length": sleeve}


# ------------------------------------------------------------------ service level
class TestGateAtChokePoint:
    def test_off_mode_no_gate_no_wire_leak(self, fake_worker, monkeypatch):
        _set_mode(monkeypatch, "off")
        fake_worker.out_colors = [_speckled(RED, 11)]
        svc = TryOnService(None)
        person = _speckled(GRAY, 7)
        out = _run(svc, person, [_g(1, "upper_outer", "long")])
        assert "sleeve_gate" not in out
        sent = fake_worker.captured[0]["garments"][0]
        assert "sleeve_length" not in sent  # gate-only metadata never reaches the worker
        assert sent["image_base64"]

    def test_observe_measures_but_never_blocks(self, fake_worker, monkeypatch):
        _set_mode(monkeypatch, "observe")
        # Worker "applied" a render that is just the person again: sleeves
        # absent -> REFUSE must be RECORDED (observe) while the render returns.
        fake_worker.out_colors = [_speckled(GRAY, 12)]
        svc = TryOnService(None)
        out = _run(svc, _speckled(GRAY, 7), [_g(1, "upper_outer", "long")])
        gate = out["sleeve_gate"]
        assert gate["mode"] == "observe"
        assert gate["layers"][0]["status"] == "REFUSE"
        assert gate["aggregate"]["layers_refused"] == 1
        assert out["rendered_image_data_url"]  # delivered — observe never blocks

    def test_observe_pass_on_changed_garment_color(self, fake_worker, monkeypatch):
        _set_mode(monkeypatch, "observe")
        fake_worker.out_colors = [_speckled(RED, 13)]
        svc = TryOnService(None)
        out = _run(svc, _speckled(GRAY, 7), [_g(1, "upper_outer", "long")])
        d = out["sleeve_gate"]["layers"][0]
        assert d["status"] == "PASS", d["reason"]
        assert out["sleeve_gate"]["threshold_source"] == "historical-defaults(unfrozen)"

    def test_enforce_without_manifest_refuses_even_a_good_render(self, fake_worker, monkeypatch):
        _set_mode(monkeypatch, "enforce")
        monkeypatch.setattr(settings, "VTON_SLEEVE_CALIBRATION_MANIFEST", "", raising=False)
        fake_worker.out_colors = [_speckled(RED, 14)]
        svc = TryOnService(None)
        with pytest.raises(RuntimeError) as ei:
            _run(svc, _speckled(GRAY, 7), [_g(1, "upper_outer", "long")])
        assert "VTON_SLEEVES_NOT_VERIFIED" in str(ei.value)
        assert "manifest" in str(ei.value)  # blocked by calibration, not by pixels

    def test_enforce_with_valid_manifest_refuses_sleeve_drop(self, fake_worker, monkeypatch, tmp_path):
        _set_mode(monkeypatch, "enforce")
        _write_valid_manifest(tmp_path, monkeypatch)
        fake_worker.out_colors = [_speckled(GRAY, 15)]  # sleeves dropped
        svc = TryOnService(None)
        with pytest.raises(RuntimeError) as ei:
            _run(svc, _speckled(GRAY, 7), [_g(1, "upper_outer", "long")])
        msg = str(ei.value)
        assert "VTON_SLEEVES_NOT_VERIFIED" in msg and "NOT present" in msg

    def test_enforce_with_valid_manifest_passes_good_render(self, fake_worker, monkeypatch, tmp_path):
        _set_mode(monkeypatch, "enforce")
        _write_valid_manifest(tmp_path, monkeypatch)
        fake_worker.out_colors = [_speckled(RED, 16)]
        svc = TryOnService(None)
        out = _run(svc, _speckled(GRAY, 7), [_g(1, "upper_outer", "long")])
        assert out["sleeve_gate"]["calibrated"] is True
        assert out["sleeve_gate"]["aggregate"]["all_sleeves_verified"] is True

    def test_enforce_undeclared_sleeve_metadata_refuses(self, fake_worker, monkeypatch, tmp_path):
        _set_mode(monkeypatch, "enforce")
        _write_valid_manifest(tmp_path, monkeypatch)
        fake_worker.out_colors = [_speckled(RED, 17)]
        svc = TryOnService(None)
        with pytest.raises(RuntimeError) as ei:
            _run(svc, _speckled(GRAY, 7), [_g(1, "upper_outer", None)])
        assert "VTON_SLEEVES_NOT_VERIFIED" in str(ei.value)
        assert "not declared" in str(ei.value)  # never guessed

    def test_observe_undecodable_garment_records_unverified(self, fake_worker, monkeypatch):
        # A garment reference the probe cannot decode must record NOT-VERIFIED
        # (observe) — never a silent pass; under enforce this same decision
        # refuses (covered by the metadata test).
        _set_mode(monkeypatch, "observe")
        fake_worker.out_colors = [_speckled(RED, 18)]
        svc = TryOnService(None)
        g = {"product_id": 2, "slot_type": "dress",
             "image_base64": "NOT-BASE64-GARBMENT-PAYLOAD",
             "sleeve_length": "long"}
        out = _run(svc, _speckled(GRAY, 7), [g])
        d = out["sleeve_gate"]["layers"][0]
        assert d["status"] == "REFUSE"
        assert "decoded" in d["reason"]  # garment image unavailable to the probe

    def test_whole_outfit_probes_outermost_and_marks_occluded(self, fake_worker, monkeypatch):
        _set_mode(monkeypatch, "observe")
        fake_worker.out_colors = [_speckled(RED, 19)]
        svc = TryOnService(None)
        garments = [_g(1, "upper_inner", "long"), _g(3, "upper_outer", "long", color=RED)]
        out = _run(svc, _speckled(GRAY, 7), garments)
        by_pid = {d.get("product_id"): d for d in out["sleeve_gate"]["layers"]}
        assert by_pid[3]["status"] == "PASS"          # outermost probed vs person
        assert by_pid[1]["status"] == "N/A"            # occluded inner layer
        assert "occlusion" in by_pid[1]["reason"]      # recorded, never silently skipped


class TestSequentialChainMerging:
    def test_per_stage_verdicts_accumulate(self, fake_worker, monkeypatch):
        _set_mode(monkeypatch, "observe")
        # stage 1: red garment over gray person -> PASS; stage 2: blue garment
        # over stage-1 red output -> PASS (changed vs the LAYER input).
        BLUE = (40, 60, 170)
        fake_worker.out_colors = [_speckled(RED, 21), _speckled(BLUE, 22)]
        svc = TryOnService(None)
        garments = [_g(1, "upper_inner", "long", color=RED),
                    _g(3, "upper_outer", "long", color=BLUE)]
        out = asyncio.run(svc._render_outfit_sequentially(
            job_id=f"seq_{UNIQUE}", person_image=_speckled(GRAY, 7),
            garments=garments, gender_mode="male", output_aspect="9:16"))
        sg_layers = out["sleeve_gate"]["layers"]
        assert [l["layer"] for l in sg_layers] == [1, 2]
        assert all(l["status"] == "PASS" for l in sg_layers)
        assert out["sleeve_gate"]["aggregate"]["layers_verified"] == 2
        # per-stage layer annotations travel with the outfit layers[]
        assert out["layers"][0]["sleeve"]["status"] == "PASS"


# --------------------------------------------------------------------- API level
class TestSyncContractHonesty:
    def test_observe_state_surfaces_in_sync_result(self, client: TestClient, fake_worker, monkeypatch):
        _set_mode(monkeypatch, "observe")
        fake_worker.out_colors = [_speckled(GRAY, 31)]
        res = client.post("/api/v1/try-on/multi-render", json={
            "product_ids": [1], "user_image_base64": _speckled(GRAY, 7)})
        assert res.status_code == 200, res.text
        assert '"sleeve_gate"' in res.text and '"observe"' in res.text

    def test_enforce_without_manifest_is_an_honest_502(self, client: TestClient, fake_worker, monkeypatch):
        _set_mode(monkeypatch, "enforce")
        monkeypatch.setattr(settings, "VTON_SLEEVE_CALIBRATION_MANIFEST", "", raising=False)
        fake_worker.out_colors = [_speckled(RED, 32)]
        res = client.post("/api/v1/try-on/multi-render", json={
            "product_ids": [1], "user_image_base64": _speckled(GRAY, 7)})
        assert res.status_code == 502, res.text
        assert "VTON_SLEEVES_NOT_VERIFIED" in res.text
        assert "data:image" not in res.text  # no image delivered on refusal

    def test_capabilities_report_gate_state_honestly(self, client: TestClient, monkeypatch):
        _set_mode(monkeypatch, "off")
        res = client.get("/api/v1/catalog/capabilities")
        assert res.status_code == 200
        data = res.json()
        body = data.get("data", data)
        flags = body.get("capabilities", body)
        sg_state = flags.get("vton_sleeve_gate")
        assert sg_state is not None and sg_state["mode"] == "off"
        assert sg_state["calibrated"] is None  # not evaluated while off


# ------------------------------------------------------------------- schema guard
class TestAdminSchemaVocabulary:
    def test_sleeve_length_literal_validation(self):
        from backend.app.schemas.admin_catalog import AdminCatalogProductCreate
        base = dict(
            category_id=1, title="Gate Tee", title_ar="تيوب البوابة",
            description="Long sleeve test product", description_ar="منتج اختبار",
            base_price="10.00", color_family="Red",
            thumbnail_url="https://cdn.invalid/a.jpg",
            skus=[{"sku_code": "SKU1", "size": "M", "color": "Red"}],
        )
        m = AdminCatalogProductCreate(**base, sleeve_length="long")
        assert m.sleeve_length == "long"
        with pytest.raises(ValueError):
            AdminCatalogProductCreate(**base, sleeve_length="mid-length")
        assert AdminCatalogProductCreate(**base).sleeve_length is None
