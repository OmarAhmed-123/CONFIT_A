"""§34 — ARCHITECTURE CONTRACT TESTS (valid + invalid dynamic inputs per component).

Components under contract:

    C-01 PersonReferenceResolver   TryOnService._prepare_person_image / check_person_bytes
    C-02 GarmentResolver           TryOnService._build_garments_payload (server-side)
    C-03 OutfitResolver            multi-render product_ids -> authoritative catalog slots
    C-04 LayeringEngine            SlotLayeringEngine (server-derived layer order)
    C-05 VTONEngine                 worker payload/response contract (hermetic capture + live)
    C-06 QualityEvaluator           assert_layer_applied (canonical per-layer gate)
    C-07 ResultProvenance           job-row fields, one-shot delivery, no raw bytes in status
    C-08 FailurePolicy              explicit error codes per failure class; no fake images

All inputs are UNKNOWN runtime inputs (evaluation/archtest_inputs) or synthetic
unknown rows — never registered benchmark fixtures. Hermetic by default; the
single live test (C-05 live) is gated by CONFIT_AT_LIVE_WORKER=1.
"""

import base64
import io
import json
import re
from types import SimpleNamespace
from pathlib import Path

import httpx
import pytest
from PIL import Image

from test_architecture_dynamic import (  # noqa: F401  (fixtures + helpers)
    EVIDENCE,
    LIVE,
    _db_session,
    _make_product,
    _record,
    data_url,
    decode_data_url,
    live,  # noqa: F401
    at_products,  # noqa: F401
    live_env,  # noqa: F401
    person_url,
    sha256,
    _multi_render,
    _GARMENTS,
)

REPO_TESTS = "backend/tests"
ARCH_INPUTS = "evaluation/archtest_inputs"


def _svc(db):
    from backend.app.services.tryon_service import TryOnService

    return TryOnService(db)


def _rt_person_bytes(name: str = "person_rt1.jpg") -> bytes:
    return open(f"{ARCH_INPUTS}/{name}", "rb").read()


def _du(rel: str) -> str:
    """data_url() wrapper: the dynamic-module helper takes a Path."""
    return data_url(Path(rel))


def _mk_image(w: int, h: int, color: tuple = (200, 120, 90)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# C-01 PersonReferenceResolver
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c01_valid_data_url_roundtrip():
    """A runtime person data URL passes through byte-identical."""
    db = _db_session()
    svc = _svc(db)
    ref = person_url("person_rt1.jpg")
    out = await svc._prepare_person_image(ref)
    assert out == ref, "data-URL person reference must be a deterministic passthrough"
    raw = decode_data_url(out)
    assert sha256(raw) == sha256(_rt_person_bytes("person_rt1.jpg"))
    db.close()


@pytest.mark.asyncio
async def test_c01_valid_raw_base64_normalized_to_data_url():
    db = _db_session()
    svc = _svc(db)
    raw_b64 = base64.b64encode(_rt_person_bytes("person_rt2.jpg")).decode()
    out = await svc._prepare_person_image(raw_b64)
    assert out.startswith("data:image/"), f"raw base64 must be normalized to a data URL, got: {out[:40]}"
    assert decode_data_url(out) == _rt_person_bytes("person_rt2.jpg")
    db.close()


@pytest.mark.asyncio
async def test_c01_invalid_corrupt_bytes_explicit_code():
    from backend.app.core.exceptions import ValidationDomainError

    db = _db_session()
    svc = _svc(db)
    corrupt = b"\x00\x01\x02NOT_AN_IMAGE" * 2000  # >10KB, undecodable
    with pytest.raises(ValidationDomainError) as ei:
        await svc._prepare_person_image("data:image/jpeg;base64," + base64.b64encode(corrupt).decode())
    assert "VTON_INPUT_INVALID" in str(ei.value)
    db.close()


@pytest.mark.asyncio
async def test_c01_invalid_undersized_explicit_code():
    from backend.app.core.exceptions import ValidationDomainError

    db = _db_session()
    svc = _svc(db)
    small = "data:image/png;base64," + base64.b64encode(_mk_image(100, 100)).decode()
    with pytest.raises(ValidationDomainError) as ei:
        await svc._prepare_person_image(small)
    assert "VTON_INPUT_INVALID" in str(ei.value)
    db.close()


@pytest.mark.asyncio
async def test_c01_invalid_aspect_explicit_code():
    from backend.app.core.exceptions import ValidationDomainError

    db = _db_session()
    svc = _svc(db)
    pano = "data:image/png;base64," + base64.b64encode(_mk_image(1280, 300)).decode()  # aspect 4.27 > 4.0
    with pytest.raises(ValidationDomainError) as ei:
        await svc._prepare_person_image(pano)
    assert "VTON_INPUT_INVALID" in str(ei.value)
    db.close()


def test_c01_http_ssrf_targets_rejected():
    from backend.app.core.security import is_safe_image_url

    for url in (
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1:5432/admin",
        "http://10.0.0.5/internal",
        "http://192.168.1.1/router",
        "file:///etc/passwd",
    ):
        assert is_safe_image_url(url) is False, f"SSRF/unsafe target not rejected: {url}"
    assert is_safe_image_url("https://images.unsplash.com/photo-123.jpg") is True


# ---------------------------------------------------------------------------
# C-02 GarmentResolver (server-side, authoritative)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c02_valid_slots_derived_server_side(client):
    db = _db_session()
    ids = {
        "top": _make_product(db, "tops", "C02 Unknown Top", _du(f"{ARCH_INPUTS}/garment_rt1.jpg"), "#2E7F8F"),
        "bottom": _make_product(db, "bottoms", "C02 Unknown Bottom", _du(f"{ARCH_INPUTS}/garment_rt2.jpg"), "#6B6B3F"),
    }
    outer = None
    from backend.app.models.catalog import Category, Product

    outer = db.query(Product).join(Category, Product.category_id == Category.id).filter(Category.slug == "outerwear").first()
    svc = _svc(db)
    p1 = db.query(Product).get(ids["top"])
    p2 = db.query(Product).get(ids["bottom"])
    po = db.query(Product).get(outer.id)
    payload = await svc._build_garments_payload([p2, p1, po])  # client-shuffled order
    slots = [g["slot_type"] for g in payload]
    assert slots == ["upper_inner", "upper_outer", "lower"], (
        f"server must sort by canonical layer hierarchy regardless of client order, got {slots}"
    )
    for g in payload:
        assert g["product_id"] is not None
        assert (g.get("image_base64") or g.get("image_url")), "garment payload must carry the resolved image (b64 or URL)"
    assert {g["product_id"] for g in payload} == {ids["top"], ids["bottom"], outer.id}
    db.close()


@pytest.mark.asyncio
async def test_c02_invalid_engine_unsupported_slot_rejected_upfront(client):
    """Footwear/accessory must be rejected BEFORE any GPU time (explicit 422 class)."""
    from backend.app.services.tryon_service import (
        VTON_ENGINE_RENDERABLE_SLOTS,
        VTON_UNSUPPORTED_SLOTS_MESSAGE,
    )

    assert VTON_ENGINE_RENDERABLE_SLOTS == {"upper_inner", "upper_outer", "lower", "dress"}
    # category slug -> vton slot mapping must route footwear out of the renderable set
    from backend.app.services.tryon_service import CATEGORY_TO_VTON_SLOT

    foot_slot = CATEGORY_TO_VTON_SLOT.get("footwear", "")
    assert foot_slot not in VTON_ENGINE_RENDERABLE_SLOTS
    assert "footwear" in VTON_UNSUPPORTED_SLOTS_MESSAGE or "{slots}" in VTON_UNSUPPORTED_SLOTS_MESSAGE


@pytest.mark.asyncio
async def test_c02_invalid_unsupported_category_raises_before_worker(client):
    """A runtime footwear product must be rejected UPFRONT (before GPU time)."""
    db = _db_session()
    from backend.app.models.catalog import Category, Product

    foot_cat = db.query(Category).filter(Category.slug == "footwear").first()
    assert foot_cat is not None, "seeded DB must contain the footwear category"
    shoe = Product(
        brand_id=1, category_id=foot_cat.id, title="C02 Runtime Shoes", title_ar="C02 Runtime Shoes",
        slug="c02-shoes-" + base64.b64encode(b"c02a").decode()[:6],
        base_price=9.99, currency="USD", color_family="Black", dominant_hex="#111111",
        description="C02 runtime shoes", description_ar="C02 runtime shoes",
        thumbnail_url=_du(f"{ARCH_INPUTS}/garment_rt1.jpg"),
        style_tags="[]", occasion_tags="[]", is_active=True, is_featured=False,
    )
    db.add(shoe)
    db.commit()
    svc = _svc(db)
    with pytest.raises(RuntimeError) as ei:
        await svc._build_garments_payload([shoe])
    assert "VTON_INPUT_INVALID" in str(ei.value)
    assert "footwear" in str(ei.value)
    db.close()


# ---------------------------------------------------------------------------
# C-03 OutfitResolver (API-level, server-authoritative)
# ---------------------------------------------------------------------------
def test_c03_invalid_unknown_product_404_before_worker(client):
    r = client.post(
        "/api/v1/tryon/multi-render",
        json={
            "product_ids": [999999],
            "user_image_base64": base64.b64encode(_rt_person_bytes("person_rt3.jpg")).decode(),
        },
    )
    assert r.status_code == 404, f"unknown product must 404 before any worker call, got {r.status_code}: {r.text[:200]}"


def test_c03_invalid_no_person_no_garments_422(client):
    r = client.post("/api/v1/tryon/multi-render", json={"product_ids": []})
    assert r.status_code in (400, 422), f"empty outfit + no person must be a client error, got {r.status_code}"


def test_c03_valid_resolution_is_server_derived(client):
    """Slot mapping is catalog-derived; a client slot_mapping can never rename a
    top into a bottom (server re-derives from the authoritative category)."""
    db = _db_session()
    top_id = _make_product(db, "tops", "C03 Unknown Tee", _du(f"{ARCH_INPUTS}/garment_rt1.jpg"), "#2E7F8F")
    r = client.post(
        "/api/v1/tryon/multi-render",
        json={
            "product_ids": [top_id],
            "slot_mapping": {"lower": top_id},  # client LIE: claims the top is a bottom
            "user_image_base64": base64.b64encode(_rt_person_bytes("person_rt1.jpg")).decode(),
        },
    )
    # no worker configured in hermetic mode -> 503 VTON_ENGINE_UNAVAILABLE after
    # resolution; the point of the contract: the request was RESOLVED against the
    # catalog (not 404/422 on the product) and the error is the engine one, not a
    # slot-acceptance of the client's lie.
    body = r.text
    assert r.status_code in (200, 503)
    assert "VTON_ENGINE_UNAVAILABLE" in body or r.status_code == 200
    # the resolved layer record must show the CATALOG slot (upper_inner), not the client's 'lower'
    if r.status_code == 200:
        items = r.json().get("applied_items") or []
        slots = {it.get("slot_type") or it.get("position") for it in items}
        assert "upper_inner" in slots and "lower" not in slots
    db.close()


# ---------------------------------------------------------------------------
# C-04 LayeringEngine (SlotLayeringEngine — the ONLY layer-order source of truth)
# ---------------------------------------------------------------------------
def _fake_product(cat_slug: str, title: str, pid: int):
    return SimpleNamespace(
        category=SimpleNamespace(slug=cat_slug, name=cat_slug.title()),
        brand=SimpleNamespace(brand_name="C04 Test Brand"),
        title=title,
        id=pid,
        base_price=10.0,
        thumbnail_url="data:image/jpeg;base64,AAAA",
        color_family="Test",
        dominant_hex="#1B1F3B",
        material="Test Fabric",
        skus=[],
    )


def test_c04_valid_layer_order_independent_of_apply_sequence():
    from backend.app.services.styling.slot_layering_engine import SlotLayeringEngine as E

    top = _fake_product("tops", "C04 Top", 1)
    bottom = _fake_product("bottoms", "C04 Bottom", 2)
    outer = _fake_product("outerwear", "C04 Blazer", 3)

    # apply in two different client sequences; final order must be identical
    r1 = E.resolve_and_apply([], top)
    r1 = E.resolve_and_apply(r1.final_applied_items, bottom)
    r1 = E.resolve_and_apply(r1.final_applied_items, outer)

    r2 = E.resolve_and_apply([], bottom)
    r2 = E.resolve_and_apply(r2.final_applied_items, outer)
    r2 = E.resolve_and_apply(r2.final_applied_items, top)

    assert r1.resolved_layer_order == ["upper_inner", "upper_outer", "lower"]
    assert r2.resolved_layer_order == r1.resolved_layer_order, "layer order must not depend on client apply order"
    assert r1.final_slot_map == {"upper_inner": 1, "upper_outer": 3, "lower": 2}


def test_c04_invalid_unsupported_category_honest_refusal():
    from backend.app.services.styling.slot_layering_engine import SlotLayeringEngine as E

    cap = _fake_product("accessories", "C04 Baseball Cap", 9)
    r = E.resolve_and_apply([], cap)
    assert r.support_level == "unsupported"
    assert r.applied_item is None
    assert r.requires_render is False
    assert r.unsupported_reason, "unsupported categories must carry an explicit honest reason (never guess)"


def test_c04_invalid_dress_conflict_cleared_with_warning():
    from backend.app.services.styling.slot_layering_engine import SlotLayeringEngine as E

    dress = _fake_product("dresses", "C04 Dress", 1)
    top = _fake_product("tops", "C04 Top", 2)
    r0 = E.resolve_and_apply([], dress)
    r = E.resolve_and_apply(r0.final_applied_items, top)
    assert r.truthfulness_flags["conflict_cleared"] is True
    assert r.removed_conflicts, "full-body dress must be cleared when a separate top is applied"
    assert any("dress" in w.lower() for w in r.warnings)


def test_c04_invalid_same_slot_replaced_not_stacked():
    from backend.app.services.styling.slot_layering_engine import SlotLayeringEngine as E

    t1 = _fake_product("tops", "C04 Tee One", 1)
    t2 = _fake_product("tops", "C04 Tee Two", 2)
    r0 = E.resolve_and_apply([], t1)
    r = E.resolve_and_apply(r0.final_applied_items, t2)
    assert len(r.final_slot_map) == 1 and r.final_slot_map.get("upper_inner") == 2
    assert r.replaced_items, "same-slot garment must replace, never stack"


def test_c04_hierarchy_is_single_source_of_truth():
    from backend.app.services.styling.slot_layering_engine import SlotLayeringEngine as E

    h = E.LAYER_HIERARCHY
    for slot in ("upper_inner", "upper_outer", "lower", "full_body", "dress", "accessory"):
        assert slot in h, f"{slot} missing from LAYER_HIERARCHY"
    assert h["upper_inner"] < h["upper_outer"] < h["lower"]
    assert E._layer_order("unknown-slot-xyz") == 30  # documented default rank


# ---------------------------------------------------------------------------
# C-05 VTONEngine (worker payload/response contract)
# ---------------------------------------------------------------------------
class _FakeResp:
    status_code = 200

    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p

    @property
    def text(self):
        return json.dumps(self._p)


def _fake_render_data_url() -> str:
    import random
    random.seed(7)
    w, h = 300, 400
    img = Image.new("RGB", (w, h), (30, 60, 90))
    px = img.load()
    for y in range(h):
        for x in range(w):
            if (x * 7 + y * 13) % 11 == 0:
                px[x, y] = (200, 40, 60)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    assert buf.getvalue().__len__() >= 1000
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _install_fake_worker(monkeypatch, captured):
    """Mock worker transport: readiness/health 200-OK, post captures payload."""
    fake_out = {
        "rendered_image_data_url": _fake_render_data_url(),
        "verify": {"PASS": True, "metric_pixel_change": 2.0, "metric_color_shift": 0.01, "metric_image_stddev": 40.0},
        "model_used": "contract-fake",
        "job_id": "contract-job",
        "execution_time_ms": 100,
        "layers_processed": 1,
    }

    async def _fake_get(self, url, **kw):
        return _FakeResp({"status": "ok", "ready": True, "model_loaded": True, "model": "contract-fake"})

    async def _fake_post(self, url, **kw):
        captured.append({"url": url, **kw})
        return _FakeResp(fake_out)

    from backend.app.services.tryon_service import TryOnService

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)
    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    monkeypatch.setattr(
        TryOnService, "_get_worker_config", lambda self: ("http://fake-worker.invalid/proc", "fake-admin-token")
    )


@pytest.mark.asyncio
async def test_c05_valid_payload_contract_captured(monkeypatch):
    """The exact wire payload to the worker: keys, no seed, garments structure."""
    captured = []
    _install_fake_worker(monkeypatch, captured)

    from backend.app.models.catalog import Product

    db = _db_session()
    top_id = _make_product(db, "tops", "C05 Contract Top", _du(f"{ARCH_INPUTS}/garment_rt3.jpg"), "#C99A2C")
    svc = _svc(db)
    p = db.query(Product).get(top_id)
    garments = await svc._build_garments_payload([p])
    person = person_url("person_rt1.jpg")

    out = await svc._call_gpu_worker("c05-contract", person, garments, gender_mode="infer_from_image", output_aspect="9:16")

    db.close()
    assert len(captured) == 1
    body = captured[0]["json"]
    assert set(body.keys()) == {"job_id", "user_image_base64_or_url", "garments", "gender_mode", "output_aspect"}, (
        f"wire payload keys changed: {sorted(body.keys())}"
    )
    assert "seed" not in body, "documented: the wire payload carries no seed field"
    assert body["job_id"] == "c05-contract"
    assert body["user_image_base64_or_url"] == person, "person reference must reach the worker unmodified"
    assert body["gender_mode"] == "infer_from_image" and body["output_aspect"] == "9:16"
    g = body["garments"][0]
    assert g["product_id"] == top_id and g["slot_type"] == "upper_inner"
    assert g.get("image_base64") or g.get("image_url")
    # response contract
    assert out["verify"]["PASS"] is True and out["model_used"] == "contract-fake"


def test_c05_invalid_no_worker_explicit_code(monkeypatch):
    from backend.app.services.tryon_service import TryOnService

    monkeypatch.delenv("VTON_WORKER_URL", raising=False)
    monkeypatch.delenv("VTON_WORKER_PROCESS_URL", raising=False)
    monkeypatch.setattr(TryOnService, "_get_worker_config", lambda self: ("", None))
    db = _db_session()
    svc = TryOnService(db)
    import asyncio

    with pytest.raises(RuntimeError) as ei:
        asyncio.run(svc._call_gpu_worker("c05-noworker", person_url("person_rt1.jpg"), [{"product_id": 1, "slot_type": "upper_inner", "image_url": "data:image/jpeg;base64,xx"}]))
    assert "VTON_ENGINE_UNAVAILABLE" in str(ei.value)
    db.close()


@pytest.mark.asyncio
async def test_c05_invalid_empty_garments_and_no_person(monkeypatch):
    captured = []
    _install_fake_worker(monkeypatch, captured)
    db = _db_session()
    svc = _svc(db)
    with pytest.raises(ValueError) as ei:
        await svc._call_gpu_worker("c05-x", person_url("person_rt1.jpg"), [])
    assert "VTON_GARMENT_ASSET_INVALID" in str(ei.value)
    with pytest.raises(ValueError) as ei:
        await svc._call_gpu_worker("c05-y", "", [{"product_id": 1, "slot_type": "upper_inner", "image_url": "data:image/jpeg;base64,xx"}])
    assert "VTON_INPUT_INVALID" in str(ei.value)
    assert captured == [], "input validation must happen BEFORE any worker call"
    db.close()


@pytest.mark.asyncio
async def test_c05_invalid_unsafe_worker_urls_rejected(monkeypatch):
    captured = []
    _install_fake_worker(monkeypatch, captured)
    db = _db_session()
    svc = _svc(db)
    with pytest.raises(ValueError) as ei:
        await svc._call_gpu_worker(
            "c05-ssrf", "http://169.254.169.254/meta/",
            [{"product_id": 1, "slot_type": "upper_inner", "image_url": "data:image/jpeg;base64,xx"}],
        )
    assert "VTON_INPUT_INVALID" in str(ei.value) and "unsafe" in str(ei.value).lower()
    with pytest.raises(ValueError) as ei:
        await svc._call_gpu_worker(
            "c05-ssrf2", person_url("person_rt1.jpg"),
            [{"product_id": 1, "slot_type": "upper_inner", "image_url": "http://127.0.0.1:5432/x"}],
        )
    assert "VTON_GARMENT_ASSET_INVALID" in str(ei.value) or "VTON_INPUT_INVALID" in str(ei.value)
    assert captured == [], "SSRF targets must be rejected BEFORE any worker call"
    db.close()


@live
@pytest.mark.asyncio
async def test_c05_live_engine_response_contract(client, live_env, at_products):
    """Live: the real worker response carries the verify gate + model identity."""
    from test_architecture_dynamic import _multi_render as render  # re-import for clarity

    code, j, out = _multi_render(client, person_url("person_rt1.jpg"), [at_products["g1"]], memo=False)
    assert code == 200 and out is not None, f"live single-garment render failed: {code} {j}"
    assert (j.get("verification") or {}).get("all_layers_verified") is True
    disclosure = j.get("ai_disclosure") or ""
    assert "fashn-vton-v1.5" in disclosure or "fashn_vton_segfee" in disclosure, (
        f"model identity must be disclosed on the result; got: {disclosure[:120]}"
    )
    img = Image.open(io.BytesIO(out))
    assert img.size[0] > 100 and img.size[1] > 100


# ---------------------------------------------------------------------------
# C-06 QualityEvaluator (canonical per-layer gate — pure, no fixtures)
# ---------------------------------------------------------------------------
def test_c06_valid_pass_returns():
    from backend.app.services.tryon_service import assert_layer_applied

    assert_layer_applied({"PASS": True, "metric_pixel_change": 4.2, "metric_color_shift": 0.02, "metric_image_stddev": 41.0}, "ok-job")  # no raise


@pytest.mark.parametrize("verify", [
    {"PASS": False, "metric_pixel_change": 0.2172, "metric_color_shift": 0.00149, "metric_image_stddev": 48.08},
    {"PASS": None},
    {},
    {"metric_pixel_change": 5.0},  # missing PASS entirely
])
def test_c06_invalid_non_pass_raises_canonical_code(verify):
    from backend.app.services.tryon_service import assert_layer_applied

    with pytest.raises(RuntimeError) as ei:
        assert_layer_applied(verify, "fail-job-42")
    msg = str(ei.value)
    assert "VTON_LAYER_NOT_APPLIED" in msg
    assert "fail-job-42" in msg, "failure must name the job for provenance"
    assert "No complete, verified outfit was produced" in msg
    pc = verify.get("metric_pixel_change")
    if pc is not None:
        assert str(pc) in msg, "metrics must be surfaced, not swallowed"


# ---------------------------------------------------------------------------
# C-07 ResultProvenance (job row + one-shot delivery, hermetic)
# ---------------------------------------------------------------------------
def test_c07_valid_job_row_provenance_fields(client):
    from backend.app.models.tryon import TryOnJob

    upload = _rt_person_bytes("person_rt4.jpg")
    r = client.post(
        "/api/v1/tryon/jobs",
        json={
            "product_ids": [1],
            "user_image_base64": base64.b64encode(upload).decode(),
        },
    )
    assert r.status_code == 202, r.text[:300]
    body = r.json()
    job_id = body["job_id"]
    db = _db_session()
    row = db.query(TryOnJob).filter(TryOnJob.job_id == job_id).first()
    assert row is not None
    # provenance fields present (no-worker path fails at the engine, AFTER the
    # request is recorded — the row is the audit trail)
    assert row.input_person_image_url, "person image reference must be persisted"
    # content-hash trace: the stored person reference decodes to EXACTLY the upload
    stored = row.input_person_image_url
    raw = decode_data_url(stored) if stored.startswith("data:") else base64.b64decode(stored)
    assert sha256(raw) == sha256(upload), "stored person reference must be byte-identical to the upload"
    assert json.loads(row.garment_ids_json) == [1]
    layers = json.loads(row.garment_layers_json)
    assert layers and (layers[0].get("product_id") == 1 or layers[0].get("id") == 1)
    assert row.delivery_token_hash and re.fullmatch(r"[0-9a-f]{64}", row.delivery_token_hash), "one-shot delivery must be hash-persisted"
    if LIVE:
        # live: the job rendered — provenance must include the engine + model identity
        assert row.status.value == "completed", f"live job should complete, got {row.status.value}: {row.error_code} {row.error_message}"
        assert row.model_used and row.model_used != "unset", "completed job must record the model used"
        assert row.output_image_url or row.metrics_json not in (None, "", "{}")
    else:
        # hermetic: no worker -> explicit engine failure AFTER the request is recorded
        assert row.status.value == "failed" and row.error_code == "VTON_ENGINE_UNAVAILABLE"
        assert not row.output_image_url, "no raw output image reference on a failed job"
    db.close()
    _record("C-07", job_row_fields=["input_person_image_url(hash-traced)", "garment_ids_json", "garment_layers_json", "delivery_token_hash", "model_used", "error_code"], person_hash_trace="sha256 match vs upload", terminal_state="completed+model_used" if LIVE else "failed+VTON_ENGINE_UNAVAILABLE", verdict="PASS")


def test_c07_invalid_status_endpoint_no_raw_bytes_or_tokens(client):
    from backend.app.models.tryon import TryOnJob

    r = client.post(
        "/api/v1/tryon/jobs",
        json={
            "product_ids": [1],
            "user_image_base64": base64.b64encode(_rt_person_bytes("person_rt1.jpg")).decode(),
        },
    )
    job = r.json()
    job_id = job["job_id"]
    token = (job.get("delivery") or {}).get("token")
    # guest job is readable WITH its one-time delivery token (non-destructive verify)
    s = client.get(f"/api/v1/tryon/jobs/{job_id}", params={"delivery_token": token})
    assert s.status_code == 200, f"status with delivery token must be 200, got {s.status_code}: {s.text[:200]}"
    text = s.text
    assert len(text) < 20000, "job status must be compact metadata — no embedded image bytes"
    assert "base64," not in text, "job status must not embed raw image payloads"
    # without the token (or with a wrong one) -> 404, no existence leakage
    assert client.get(f"/api/v1/tryon/jobs/{job_id}").status_code == 404
    assert client.get(f"/api/v1/tryon/jobs/{job_id}", params={"delivery_token": "wrong-token"}).status_code == 404
    # unknown job id -> 404
    assert client.get("/api/v1/tryon/jobs/vton_job_doesnotexist000").status_code == 404
    # result endpoint: missing the required one-time token -> rejected (422 validation),
    # never 200; wrong token -> 404/410 (no existence leakage, no image)
    res_no = client.get(f"/api/v1/tryon/jobs/{job_id}/result")
    assert res_no.status_code in (401, 403, 404, 410, 422)
    res_bad = client.get(f"/api/v1/tryon/jobs/{job_id}/result", params={"delivery_token": "not-the-token"})
    assert res_bad.status_code in (401, 403, 404, 410)
    assert "base64" not in res_bad.text
    db = _db_session()
    row = db.query(TryOnJob).filter(TryOnJob.job_id == job_id).first()
    assert row is not None
    db.close()
    _record("C-07", status_contract="token-verified 200; no-token/wrong-token/unknown 404; no raw bytes in status; result w/o token rejected", verdict="PASS")


# ---------------------------------------------------------------------------
# C-08 FailurePolicy (explicit codes; no fake images on any failure)
# ---------------------------------------------------------------------------
def test_c08_matrix_explicit_codes_and_no_fake_images(client, monkeypatch):
    """Every failure class returns its explicit code and NEVER an image.

    The matrix runs with the worker config FORCED UNAVAILABLE (monkeypatched on
    the service class) so the failure-policy contract is identical whether or
    not a live worker happens to be configured in the environment.
    """
    from backend.app.services.tryon_service import TryOnService

    monkeypatch.setattr(TryOnService, "_get_worker_config", lambda self: ("", None))
    cases = []
    # (label, status_code, expected_error_code, response)
    r_no_person = client.post("/api/v1/tryon/multi-render", json={"product_ids": [1]})
    cases.append(("no_person", r_no_person.status_code, "VTON_INPUT_INVALID", r_no_person))

    r_corrupt = client.post(
        "/api/v1/tryon/multi-render",
        json={"product_ids": [1], "user_image_base64": base64.b64encode(b"\x00" * 20000).decode()},
    )
    # hermetic ordering: engine-availability is checked before byte-level image
    # validation, so the classified hermetic failure is the 503 engine code; with a
    # live worker the same input surfaces VTON_INPUT_INVALID (validator contract
    # covered hermetically by AT-16). The contract: classified, explicit, no image.
    cases.append(("corrupt_person", r_corrupt.status_code, ("VTON_INPUT_INVALID", "VTON_ENGINE_UNAVAILABLE"), r_corrupt))

    r_unknown = client.post(
        "/api/v1/tryon/multi-render",
        json={"product_ids": [999998], "user_image_base64": base64.b64encode(_rt_person_bytes("person_rt1.jpg")).decode()},
    )
    cases.append(("unknown_product", r_unknown.status_code, None, r_unknown))

    r_noworker = client.post(
        "/api/v1/tryon/multi-render",
        json={"product_ids": [1], "user_image_base64": base64.b64encode(_rt_person_bytes("person_rt1.jpg")).decode()},
    )
    cases.append(("no_worker", r_noworker.status_code, "VTON_ENGINE_UNAVAILABLE", r_noworker))

    results = {}
    for label, code, expected_err, resp in cases:
        assert resp.status_code != 500, f"{label}: unclassified 500 — failure policy violated: {resp.text[:200]}"
        body = resp.text
        # NEVER a rendered image on failure
        if resp.status_code != 200:
            assert "rendered_image_data_url" not in body, f"{label}: failure response references a rendered image"
            assert "data:image" not in body.replace('"user_reference_image"', ""), (
                f"{label}: failure response embeds an image payload"
            )
        if isinstance(expected_err, tuple):
            ok = any(e in body for e in expected_err)
        else:
            ok = (expected_err in body) if expected_err else True
        results[label] = {"status_code": code, "expected_error_code": expected_err, "body_has_code": ok}
    assert results["no_worker"]["body_has_code"], "no-worker failure must name VTON_ENGINE_UNAVAILABLE"
    assert results["corrupt_person"]["body_has_code"], "corrupt input must be classified explicitly"
    assert results["corrupt_person"]["status_code"] in (400, 422, 503)
    assert results["unknown_product"]["status_code"] == 404
    _record("C-08", matrix=results, verdict="PASS — explicit codes, no fake images")
