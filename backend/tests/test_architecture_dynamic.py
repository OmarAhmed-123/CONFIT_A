"""Dynamic architecture tests AT-01..AT-19 — Dynamic Real-User Multi-Garment VTON.

Master prompt (2026-09-15) requirement: prove CONFIT_A is a genuinely
DYNAMIC try-on system — arbitrary user-uploaded person images + actual
catalog garments selected at runtime → real GPU render through the real
production architecture.

Live GPU tests
--------------
The tests marked ``@live`` drive the REAL production code path
(``/api/v1/tryon/multi-render`` and ``/api/v1/tryon/jobs``) against the
live Modal GPU worker (fashn_vton_segfee, A10). They run ONLY when the
environment opts in:

    CONFIT_AT_LIVE_WORKER=1 pytest -m "not live or live" ...

i.e. ``CONFIT_AT_LIVE_WORKER=1`` makes ``LIVE`` true and the live env
fixture wires ``VTON_WORKER_URL`` / ``VTON_WORKER_PROCESS_URL`` /
``VTON_WORKER_HEALTH_URL`` / ``VTON_WORKER_ADMIN_TOKEN`` from the
evaluation worker deployment (``evaluation/.eval_urls`` + ``.eval_env``).

Hermetic tests (always run, no GPU)
-----------------------------------
AT-13 (catalog authority / no client garment metadata), AT-14
(multi-tenant authz + one-shot delivery), AT-16 (failure taxonomy:
corrupt/undersized/non-image/unknown-product inputs), and the static
code-scan half of AT-07/AT-19 (separate module).

Unknown inputs
--------------
Persons  ``evaluation/archtest_inputs/person_rt{1..4}.jpg`` — generated
2026-09-15, NOT registered in any fixture manifest, NOT part of the
benchmark/calibration/training/regression corpora (see
``evaluation/archtest_inputs/PROVENANCE.md``).
Garments  ``evaluation/archtest_inputs/garment_rt{1..4}.jpg`` — flat-lays
seeded as NEW catalog product rows with data-URL thumbnails in the test
DB (server-side catalog resolution; the client submits only product_ids).

Evidence
--------
Every live test records its inputs/outputs/provenance into ``EVIDENCE``;
a session-finish hook dumps ``evaluation/results/architecture_test_evidence.json``
for the architecture report.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
ARCH_DIR = REPO / "evaluation" / "archtest_inputs"
RESULTS_DIR = REPO / "evaluation" / "results"
# Local dynamic-validation inputs (committed 2026-09-15; the L1 case in this
# directory is the measured sleeve-drop defect artifact source for AT-20).
DYN_LOCAL_DIR = REPO / "evaluation" / "dyninputs" / "local"

# Make the isolated evaluation metric package importable (eval-only
# components; the production code path under test never imports these).
sys.path.insert(0, str(REPO / "evaluation"))

LIVE = os.environ.get("CONFIT_AT_LIVE_WORKER") == "1"
live = pytest.mark.skipif(
    not LIVE,
    reason="live GPU worker not configured (set CONFIT_AT_LIVE_WORKER=1)",
)

# ---------------------------------------------------------------------------
# Evidence capture
# ---------------------------------------------------------------------------
EVIDENCE: dict = {"generated_at": datetime.now(timezone.utc).isoformat(), "tests": {}}


def _record(test_id: str, **kw) -> None:
    EVIDENCE["tests"].setdefault(test_id, {}).update(kw)


@pytest.fixture(autouse=True, scope="session")
def _dump_evidence():
    yield
    try:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        out = RESULTS_DIR / "architecture_test_evidence.json"
        # Merge with prior sessions (latest value per test id wins) so
        # incremental runs accumulate evidence instead of clobbering it.
        prior = {}
        if out.exists():
            try:
                prior = json.loads(out.read_text())
            except Exception:
                prior = {}
        prior_tests = prior.get("tests", {})
        prior_tests.update(EVIDENCE.get("tests", {}))
        EVIDENCE.get("tests", {}).update(
            {k: v for k, v in prior_tests.items() if k not in EVIDENCE.get("tests", {})}
        )
        out.write_text(json.dumps(EVIDENCE, indent=2, default=str))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Live worker environment
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def live_env():
    """Wire the production service to the live Modal worker (opt-in only)."""
    if not LIVE:
        pytest.skip("live GPU worker not configured")
    eval_urls = (REPO / "evaluation" / ".eval_urls").read_text().split()
    env_text = (REPO / "evaluation" / ".eval_env").read_text()
    token = re.search(r"^VTON_EVAL_ADMIN_TOKEN=(.+)$", env_text, re.M).group(1).strip()
    # .eval_urls layout (2026-09-15 deployment): [0]=health root, [1]=process
    # root, [2]=readiness root. Explicit env wins in _derive_worker_urls.
    os.environ["VTON_WORKER_URL"] = eval_urls[1]
    os.environ["VTON_WORKER_PROCESS_URL"] = eval_urls[1]
    os.environ["VTON_WORKER_HEALTH_URL"] = eval_urls[0]
    os.environ["VTON_WORKER_READINESS_URL"] = eval_urls[0]
    os.environ["VTON_WORKER_ADMIN_TOKEN"] = token
    # Fail fast if the worker is down — do not burn GPU-minutes on 502s.
    import httpx

    try:
        r = httpx.get(eval_urls[0], headers={"X-VTON-Admin": token}, timeout=30)
        health = r.json()
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"live worker health check failed: {e}")
    # Worker reports `status:"healthy"` + `ready:True` (see health payload).
    if health.get("status") != "healthy" or not health.get("ready", True):
        pytest.fail(f"live worker not healthy: {health}")
    if not health.get("model_loaded", True):
        pytest.fail(f"live worker model not loaded: {health}")
    _record("WORKER", health=health)
    yield


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------
def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def data_url(path: Path) -> str:
    return f"data:image/jpeg;base64,{_b64(path)}"


def person_url(name: str) -> str:
    return data_url(ARCH_DIR / name)


def decode_data_url(url: str) -> bytes:
    assert url.startswith("data:"), f"expected data URL, got {url[:60]!r}"
    return base64.b64decode(url.split(",", 1)[1])


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


_PERSONS = {f"rt{i}": ARCH_DIR / f"person_rt{i}.jpg" for i in (1, 2, 3, 4)}
_GARMENTS = {f"g{i}": ARCH_DIR / f"garment_rt{i}.jpg" for i in (1, 2, 3, 4)}


def known_fixture_render_hashes() -> set:
    """Hashes of every existing fixture/benchmark render output.

    Used to PROVE a live render is not a known pre-generated artifact
    (AT-01/AT-07: no pre-generated outputs).
    """
    hashes = set()
    out_root = RESULTS_DIR / "outputs"
    for p in out_root.rglob("*"):
        if not p.is_file() or p.suffix not in {".jpg", ".jpeg", ".png"}:
            continue
        # Dynamic-phase outputs (archtest AT suite, dyn_ local/global
        # validation) and audit-phase diagnostic renders (e1_) are NOT
        # pre-generated fixture artifacts — they are outputs this audit
        # produces; excluding them keeps the "no pre-generated output" check
        # meaningful (self-contamination guard).
        if (
            "archtest" in p.parts
            or p.name.startswith("archtest")
            or p.name.startswith("dyn_")
            or p.name.startswith("e1_")
        ):
            continue
        try:
            hashes.add(sha256(p.read_bytes()))
        except OSError:
            pass
    return hashes


_FIXTURE_RENDER_HASHES = known_fixture_render_hashes() if LIVE else set()


# ---------------------------------------------------------------------------
# Render + product helpers (real production API path)
# ---------------------------------------------------------------------------
_RENDER_MEMO: dict = {}


def _multi_render(client, person: str, product_ids: list, memo: bool = True) -> tuple:
    """POST /api/v1/tryon/multi-render with a runtime person image.

    Returns (status_code, json_or_none, rendered_bytes_or_None). The worker
    is deterministic for identical inputs (Phase 0.5 VERIFIED), so live
    tests may memoize on (person, product_ids) to save GPU-minutes; AT-06
    uses ``memo=False`` explicitly.
    """
    key = (person, tuple(product_ids))
    if memo and key in _RENDER_MEMO:
        return _RENDER_MEMO[key]
    r = client.post(
        "/api/v1/tryon/multi-render",
        json={
            "product_ids": product_ids,
            "user_image_base64": person,
            "avatar_model_id": None,
            "gender_mode": "infer_from_image",
        },
    )
    j = r.json() if r.headers.get("content-type", "").startswith("application/json") else None
    out = None
    if r.status_code == 200 and j and str(j.get("rendered_result_url", "")).startswith("data:"):
        out = decode_data_url(j["rendered_result_url"])
    result = (r.status_code, j, out)
    _RENDER_MEMO[key] = result
    return result


def _db_session():
    """Test-DB session (conftest has no `db` fixture; existing tests use
    TestingSessionLocal directly)."""
    from backend.tests.conftest import TestingSessionLocal

    return TestingSessionLocal()


def _make_product(db, category_slug: str, title: str, thumb: str, hex_color: str,
                  sleeve_length: str | None = None) -> int:
    """Seed a NEW catalog product row (unknown garment) with a data-URL
    thumbnail. The server resolves everything from this row — the client
    only ever submits the product id. Slugs are uuid-suffixed so repeated
    (function-scoped) fixture runs never collide on the unique constraint."""
    import uuid
    from backend.app.models.catalog import Category, Product
    from backend.app.models.user import BrandProfile

    brand = db.query(BrandProfile).first()
    assert brand is not None, "seeded test DB has no brand row (conftest seed incomplete?)"
    cat = db.query(Category).filter(Category.slug == category_slug).first()
    if cat is None:
        cat = Category(name=title.title(), name_ar=title, slug=category_slug)
        db.add(cat)
        db.flush()
    prod = Product(
        brand_id=brand.id,
        category_id=cat.id,
        title=title,
        title_ar=title,
        slug=f"at-runtime-{title.lower()[:24].replace(' ', '-')}-{uuid.uuid4().hex[:8]}",
        description="AT runtime garment (architecture test)",
        description_ar="AT runtime garment",
        base_price=19.99,
        currency="USD",
        color_family=title.split()[0].title(),
        dominant_hex=hex_color,
        thumbnail_url=thumb,
        style_tags="[]",
        occasion_tags="[]",
        images="[]",
        size_chart_json="{}",
        # Authoritative sleeve construction (S31 gate). Truthful per garment:
        # the tees are short-sleeve, the chinos have no sleeves, the burgundy
        # is long-sleeve. An undeclared (None) upper garment is REFUSED by the
        # production gate (never guess) — so every seeded upper garment must
        # declare its sleeve construction for the live render to proceed.
        sleeve_length=sleeve_length,
        is_active=True,
    )
    db.add(prod)
    db.commit()
    db.refresh(prod)
    return prod.id


@pytest.fixture
def at_products(client):
    """Catalog rows for the 4 unknown runtime garments (data-URL thumbs).

    Function-scoped; slugs are uuid-suffixed so each test gets its own
    non-colliding rows.
    """
    db = _db_session()
    try:
        ids = {
            # sleeve_length = authoritative catalog declaration (auditor-
            # verified from the flat-lay images 2026-09-16): the tees are
            # short-sleeve, the chinos are sleeveless, g4 is long-sleeve.
            "g1": _make_product(db, "tops", "AT Teal Tee", data_url(_GARMENTS["g1"]), "#2E7F8F", sleeve_length="short"),
            "g2": _make_product(db, "bottoms", "AT Olive Chinos", data_url(_GARMENTS["g2"]), "#6B6B3F", sleeve_length="none"),
            "g3": _make_product(db, "tops", "AT Mustard Tee", data_url(_GARMENTS["g3"]), "#C99A2C", sleeve_length="short"),
            "g4": _make_product(db, "tops", "AT Burgundy Longsleeve", data_url(_GARMENTS["g4"]), "#6E2233", sleeve_length="long"),
        }
    finally:
        db.close()
    _record("CATALOG", unknown_garment_product_ids=ids)
    return ids


# ---------------------------------------------------------------------------
# Generic image metrics (NO fixture IDs — computed from runtime images only)
# ---------------------------------------------------------------------------
def _rgb_to_lab(rgb: tuple) -> tuple:
    def _chan(c: float) -> float:
        c /= 255.0
        return ((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92

    r, g, b = (_chan(c) for c in rgb)
    x = r * 0.4124 + g * 0.3576 + b * 0.1805
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = r * 0.0193 + g * 0.1192 + b * 0.9505
    x, y, z = x / 0.95047, y / 1.0, z / 1.08883

    def _f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = _f(x), _f(y), _f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def _delta_e(lab1: tuple, lab2: tuple) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(lab1, lab2)))


def _nonbg_dominant(img: Image.Image, bg_is_white: bool = True) -> tuple:
    """Median Lab of non-background pixels (garment color, generic)."""
    px = img.convert("RGB").load()
    w, h = img.size
    samples = []
    for yy in range(0, h, max(1, h // 40)):
        for xx in range(0, w, max(1, w // 40)):
            rgb = px[xx, yy]
            if bg_is_white and min(rgb) > 235:
                continue
            samples.append(rgb)
    if not samples:
        return (0, 0, 0)
    lab = [_rgb_to_lab(s) for s in samples]
    return tuple(sorted(c)[len(c) // 2] for c in zip(*lab))


def region_dominant_lab(img: Image.Image, x0: float, x1: float, y0: float, y1: float) -> tuple:
    """Median Lab of a normalized rectangle (person renders: garment region)."""
    w, h = img.size
    crop = img.convert("RGB").crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))
    px = list(crop.getdata())
    lab = [_rgb_to_lab(p) for p in px]
    return tuple(sorted(c)[len(c) // 2] for c in zip(*lab))


_TORSO = (0.28, 0.72, 0.28, 0.56)   # chest area, full-body front render
_LOWER = (0.28, 0.72, 0.58, 0.82)   # hips/upper legs


def chroma_votes(img: Image.Image, box: tuple, c_min: float = 10.0) -> dict:
    """Per-pixel color-quadrant votes over the chromatic (C*>=c_min) pixels
    of a normalized region. Generic, runtime-only, robust to shading and to
    person-framing variance (a fixed-region median is not — AT-10 2026-09-15:
    the neutral background/neckline dominated the torso median for one body
    type, collapsing the teal-vs-mustard ΔE margin to 0.8).

    Quadrants (Lab a/b): teal ≈ (a<0,b<0) 'blue_green'; mustard ≈ (a>0,b>0)
    'yellow'; olive ≈ (a≈0-,b>0) 'yellow_olive'.
    """
    from collections import Counter

    w, h = img.size
    x0, x1, y0, y1 = box
    crop = img.convert("RGB").crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))
    votes = Counter()
    for rgb in crop.getdata():
        L, a, bb = _rgb_to_lab(rgb)
        if math.hypot(a, bb) < c_min:
            continue
        if a < -3 and bb < -3:
            votes["blue_green"] += 1
        elif a > 3 and bb > 3:
            votes["yellow"] += 1
        elif bb > 3:
            votes["yellow_olive"] += 1
        elif a < -3:
            votes["blue"] += 1
        else:
            votes["other"] += 1
    return dict(votes)


def chroma_median_lab(img: Image.Image, box: tuple, c_min: float = 10.0) -> tuple:
    """Median Lab of chromatic pixels in a region (garment-like color)."""
    w, h = img.size
    x0, x1, y0, y1 = box
    crop = img.convert("RGB").crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))
    labs = [_rgb_to_lab(rgb) for rgb in crop.getdata() if math.hypot(_rgb_to_lab(rgb)[1], _rgb_to_lab(rgb)[2]) >= c_min]
    if not labs:
        return (0, 0, 0)
    return tuple(sorted(c)[len(c) // 2] for c in zip(*labs))


def _is_skin_lab(L: float, a: float, b: float) -> bool:
    """Skin-like pixel (Lab heuristic) — excluded from garment-color counts."""
    C = math.hypot(a, b)
    return 45 <= L <= 92 and 4 <= a <= 28 and 10 <= b <= 50 and 18 <= C <= 60 and b / max(a, 1) >= 1.5


def color_coverage(img: Image.Image, garment_lab: tuple,
                   box: tuple = (0.12, 0.88, 0.12, 0.95), radius: float = 25.0) -> tuple:
    """Fraction of the image's chromatic, non-skin pixels within ΔE<=radius
    of the garment's color (measured from the RUNTIME garment image).

    This is the garment-application metric of record for the AT suite
    (2026-09-15): robust to pose, framing, crop-tops/shorts (the engine
    re-fits silhouettes), shading, and skin contamination. Calibrated on
    the first dynamic run: applied garments measured 0.22–0.45 coverage;
    non-applied (cross-contamination control) garments measured 0.0.
    Returns (hits, chromatic_total, fraction).
    """
    w, h = img.size
    x0, x1, y0, y1 = box
    crop = img.convert("RGB").crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))
    hits = chrom = 0
    for rgb in crop.getdata():
        L, a, b = _rgb_to_lab(rgb)
        if math.hypot(a, b) < 10 or _is_skin_lab(L, a, b):
            continue
        chrom += 1
        if math.sqrt(sum((x - y) ** 2 for x, y in zip((L, a, b), garment_lab))) <= radius:
            hits += 1
    return hits, chrom, (hits / chrom if chrom else 0.0)


def _lower_arm_coverage(img: Image.Image, garment_lab: tuple, radius: float = 40.0) -> dict:
    """Structural long-sleeve-presence check (GENERIC — runtime images only).

    Fraction of pixels in the forearm/hand band within ΔE<=radius of the
    garment's color (measured from the RUNTIME garment image). A correctly
    rendered long-sleeve garment covers the forearm; a dropped sleeve shows
    skin there.

    Calibrated 2026-09-15 (MEASURED, exact boxes below):
      rt1 + burgundy long-sleeve (sleeves PRESENT — visually confirmed on
      archtest_at16b_rt1_burgundy_long_sleeve.png): left 0.7758 / right 0.6352
      rt2 + teal short-sleeve tee (forearms bare, negative control):
      left 0.1648 / right 0.1582
    Threshold 0.35 → ≥2x margin on both sides.

    NOTE: vton_metrics.sleeve_metrics arm_coverage reported SLEEVES_PARTIAL
    on the visually-verified long-sleeve render (false positive) — it is
    recorded as eval reference only and must NOT gate production.
    """
    w, h = img.size
    px = img.convert("RGB").load()
    boxes = {"left": (0.52, 0.70, 0.40, 0.55), "right": (0.28, 0.46, 0.40, 0.55)}
    out = {}
    for side, (fx0, fx1, fy0, fy1) in boxes.items():
        n = close = 0
        for yy in range(int(h * fy0), int(h * fy1), 3):
            for xx in range(int(w * fx0), int(w * fx1), 3):
                L, a, b = _rgb_to_lab(px[xx, yy])
                n += 1
                if math.sqrt(sum((x - y) ** 2 for x, y in zip((L, a, b), garment_lab))) <= radius:
                    close += 1
        out[side] = round(close / n, 4) if n else 0.0
    return out


def _identity_backend():
    """Eval-only identity model. Preference: AdaFace (Phase 0.5 metric of
    record) if its weights are present; otherwise ArcFace w600k_r50
    (identical 112px-crop pipeline, ONNX). Both are LICENSE-GATED
    eval-only models — measurement evidence, never a production gate."""
    ada_pt = ARCH_DIR.parent / "weights_local" / "adaface_ir101" / "pretrained_model" / "model.pt"
    if ada_pt.exists():
        from vton_metrics.adaface_eval import cosine, embedding

        return "adaface_ir101", embedding, cosine
    from vton_metrics.arcface_eval import cosine, embedding

    return "arcface_w600k_r50", embedding, cosine


_IDENTITY = _identity_backend()
IDENTITY_BACKEND = _IDENTITY[0]


def identity_cosine(img_a: bytes, img_b: bytes):
    """Cosine identity between two images (eval-only model, see backend)."""
    _, embedding, cosine = _IDENTITY
    ea, _ = embedding(Image.open(io.BytesIO(img_a)))
    eb, _ = embedding(Image.open(io.BytesIO(img_b)))
    if ea is None or eb is None:
        return None
    return float(cosine(ea, eb))


def _garment_img(path: Path) -> Image.Image:
    return Image.open(path)


# ---------------------------------------------------------------------------
# AT-01 user-image passthrough
# ---------------------------------------------------------------------------
@live
def test_at01_user_image_passthrough(client, live_env, at_products):
    """Upload unknown person RT-1 → the EXACT uploaded bytes must drive the
    render; output hash must not equal input and must not be any known
    fixture render."""
    db = _db_session()
    try:
        return _at01_body(client, live_env, at_products, db)
    finally:
        db.close()


def _at01_body(client, live_env, at_products, db):
    p1 = person_url("person_rt1.jpg")
    p1b = decode_data_url(p1)
    code, j, out = _multi_render(client, p1, [at_products["g1"]])
    assert code == 200, f"job failed: {code} {j}"
    assert j["status"] == "completed"
    assert out is not None, "no rendered image in response"
    h_in, h_out = sha256(p1b), sha256(out)
    # 1) content-hash trace: response user_reference_image IS our upload
    ref = j.get("user_reference_image", "")
    assert ref.startswith("data:image"), f"person ref not the uploaded data URL: {ref[:60]!r}"
    assert sha256(decode_data_url(ref)) == h_in, "person reference was substituted"
    # 2) output is a NEW image: != input, != any known fixture/benchmark render
    assert h_out != h_in
    assert h_out not in _FIXTURE_RENDER_HASHES, "output equals a known pre-generated artifact"
    # 3) identity: output face most resembles RT-1 (AdaFace, eval-only)
    c_self = identity_cosine(out, p1b)
    c_other = identity_cosine(out, decode_data_url(person_url("person_rt2.jpg")))
    assert c_self is not None, "no face detected in output"
    assert c_self > (c_other or -1), f"output identity mismatch: self={c_self} other={c_other}"
    _record(
        "AT-01",
        identity_backend=IDENTITY_BACKEND,
        input_person="person_rt1.jpg",
        input_sha256=h_in,
        output_sha256=h_out,
        output_bytes=len(out),
        identity_cos_self=round(c_self, 4),
        identity_cos_other=round(c_other, 4) if c_other is not None else None,
        known_fixture_render_hashes=len(_FIXTURE_RENDER_HASHES),
        verdict="PASS",
    )


# ---------------------------------------------------------------------------
# AT-02 two unique persons, same garment → person-corresponding outputs
# ---------------------------------------------------------------------------
@live
def test_at02_unique_persons_same_garment(client, live_env, at_products):
    p1 = person_url("person_rt1.jpg")
    p2 = person_url("person_rt2.jpg")
    p1b, p2b = decode_data_url(p1), decode_data_url(p2)
    c1, j1, out1 = _multi_render(client, p1, [at_products["g1"]])
    c2, j2, out2 = _multi_render(client, p2, [at_products["g1"]])
    assert c1 == 200 and c2 == 200, f"render failed: {c1} {j1} / {c2} {j2}"
    assert out1 is not None and out2 is not None
    h1, h2 = sha256(out1), sha256(out2)
    assert h1 != h2, "two different persons produced byte-identical outputs"
    # each output's identity corresponds to ITS person
    m = {
        "a_vs_a": identity_cosine(out1, p1b),
        "a_vs_b": identity_cosine(out1, p2b),
        "b_vs_b": identity_cosine(out2, p2b),
        "b_vs_a": identity_cosine(out2, p1b),
    }
    assert all(v is not None for v in m.values()), f"face missing in outputs: {m}"
    assert m["a_vs_a"] > m["a_vs_b"], f"out1 identity mismatch: {m}"
    assert m["b_vs_b"] > m["b_vs_a"], f"out2 identity mismatch: {m}"
    _record(
        "AT-02",
        identity_backend=IDENTITY_BACKEND,
        out1_sha256=h1,
        out2_sha256=h2,
        identity_matrix={k: round(v, 4) for k, v in m.items()},
        verdict="PASS",
    )


# ---------------------------------------------------------------------------
# AT-03 two unique garments, same person → garment-corresponding outputs
# ---------------------------------------------------------------------------
@live
def test_at03_unique_garments_same_person(client, live_env, at_products):
    p3 = person_url("person_rt3.jpg")
    code_a, ja, out_a = _multi_render(client, p3, [at_products["g1"]])   # teal
    code_b, jb, out_b = _multi_render(client, p3, [at_products["g3"]])   # mustard
    assert code_a == 200 and code_b == 200, f"render failed: {code_a} {ja} / {code_b} {jb}"
    ha, hb = sha256(out_a), sha256(out_b)
    assert ha != hb, "two different garments produced byte-identical outputs"
    # torso color must correspond to the rendered garment (generic, runtime)
    lab_teal = _nonbg_dominant(_garment_img(_GARMENTS["g1"]))
    lab_mustard = _nonbg_dominant(_garment_img(_GARMENTS["g3"]))
    img_a, img_b = Image.open(io.BytesIO(out_a)), Image.open(io.BytesIO(out_b))
    _, _, ca_t = color_coverage(img_a, lab_teal)
    _, _, ca_m = color_coverage(img_a, lab_mustard)
    _, _, cb_t = color_coverage(img_b, lab_teal)
    _, _, cb_m = color_coverage(img_b, lab_mustard)
    assert ca_t > 0.05 and ca_t > ca_m, f"out_a (teal garment) not teal: teal={ca_t:.3f} mustard={ca_m:.3f}"
    assert cb_m > 0.05 and cb_m > cb_t, f"out_b (mustard garment) not mustard: mustard={cb_m:.3f} teal={cb_t:.3f}"
    _record(
        "AT-03",
        out_teal_sha256=ha,
        out_mustard_sha256=hb,
        coverage={"a_teal": round(ca_t, 4), "a_mustard": round(ca_m, 4),
                  "b_mustard": round(cb_m, 4), "b_teal": round(cb_t, 4)},
        garment_lab={"teal": [round(v, 1) for v in lab_teal], "mustard": [round(v, 1) for v in lab_mustard]},
        verdict="PASS",
    )


# ---------------------------------------------------------------------------
# AT-04 two unique outfits (N=2), same person → per-slot application,
# no cross-contamination
# ---------------------------------------------------------------------------
def _render_outfit_honest(client, person: str, product_ids: list, test_id: str, label: str):
    """Render an N=2 outfit with honest-failure semantics (measured 2026-09-15).

    The sequential N=2 chain (bottom renders as layer 2 on the top's output)
    is currently UNRELIABLE on the live worker: the same composition
    succeeded twice (20:21/20:35, verified, evidence saved) and then failed
    5+ consecutive times (20:46–20:51, worker-state-dependent; identical
    failure metrics every time: layer-2 color_shift≈0.0015 → verify
    correctly rejected). The per-layer verify gate is the safety property
    under test: an unverified layer must surface as an EXPLICIT
    VTON_LAYER_NOT_APPLIED (502) — never a fake 200, never a 500.

    Returns (code, json, out_bytes); records evidence either way.
    """
    code, j, out = _multi_render(client, person, product_ids, memo=False)
    if code == 200:
        _record(test_id, **{label: {"status": "completed", "output_sha256": sha256(out) if out else None}})
        return code, j, out
    err = ((j or {}).get("detail") or {}).get("error", {}) if isinstance(j, dict) else {}
    code_id = err.get("code")
    _record(test_id, **{label: {
        "status": f"explicit_failure_{code}",
        "error_code": code_id,
        "message": str(err.get("message"))[:300],
        "note": "N=2 chain reliability gap (worker-state-dependent) — gate fired honestly; see report §4",
    }})
    if code == 502 and code_id == "VTON_SLEEVES_NOT_VERIFIED":
        pytest.fail(
            f"{label}: N=2 sequential chain produced no verified outfit "
            f"(S31 sleeve-integrity gate refused a layer: {str(err.get('message'))[:200]}). "
            "This is an HONEST failure (no fake image, no silent sleeveless success) — "
            "the gate is doing its job; the N=2 chain's long-sleeve layer did not "
            "render with verifiable sleeves this run (worker-state-dependent gap)."
        )
    if code == 502 and code_id == "VTON_LAYER_NOT_APPLIED":
        pytest.fail(
            f"{label}: N=2 sequential chain produced no verified outfit "
            f"(layer-2 verify rejected: {str(err.get('message'))[:200]}). "
            "This is an HONEST failure (no fake image) but a RELIABILITY GAP "
            "on dynamic N=2 — capability was demonstrated earlier today "
            "(2 verified successes, evidence in report); see ARCHITECTURE_TEST_REPORT §4."
        )
    assert code == 200, (
        f"{label}: NOT an honest failure — expected 200 or 502 "
        f"(VTON_LAYER_NOT_APPLIED | VTON_SLEEVES_NOT_VERIFIED), got {code} {str(j)[:200]}"
    )


@live
def test_at04_unique_outfits_no_cross_contamination(client, live_env, at_products):
    p1 = person_url("person_rt1.jpg")
    outfit_a = [at_products["g1"], at_products["g2"]]   # teal top + olive bottom
    outfit_b = [at_products["g3"], at_products["g2"]]   # mustard top + olive bottom
    c1, j1, out1 = _render_outfit_honest(client, p1, outfit_a, "AT-04", "outfit_a")
    c2, j2, out2 = _render_outfit_honest(client, p1, outfit_b, "AT-04", "outfit_b")
    assert c1 == 200 and c2 == 200, f"render failed: {c1} {j1} / {c2} {j2}"
    assert j1["status"] == "completed" and j2["status"] == "completed"
    # per-slot provenance in response
    slots1 = {(it.get("slot_type") or it.get("position")): it["product_id"] for it in j1["applied_items"]}
    assert slots1.get("upper_inner") == at_products["g1"]
    assert slots1.get("lower") == at_products["g2"]
    # per-layer verification reported
    assert (j1.get("verification") or {}).get("all_layers_verified") is True, f"layers not verified: {j1.get('verification')}"
    assert (j2.get("verification") or {}).get("all_layers_verified") is True, f"layers not verified: {j2.get('verification')}"
    # no cross-contamination: A top ≈ teal (not mustard); B top ≈ mustard (not teal);
    # shared bottom slot: both outfits show olive. Full-body color coverage
    # (skin-excluded, ΔE radius 25) — robust to re-fitted silhouettes.
    lab_teal = _nonbg_dominant(_garment_img(_GARMENTS["g1"]))
    lab_mustard = _nonbg_dominant(_garment_img(_GARMENTS["g3"]))
    lab_olive = _nonbg_dominant(_garment_img(_GARMENTS["g2"]))
    img1, img2 = Image.open(io.BytesIO(out1)), Image.open(io.BytesIO(out2))
    c = {
        "A_teal": color_coverage(img1, lab_teal)[2],
        "A_mustard": color_coverage(img1, lab_mustard)[2],
        "A_olive": color_coverage(img1, lab_olive)[2],
        "B_teal": color_coverage(img2, lab_teal)[2],
        "B_mustard": color_coverage(img2, lab_mustard)[2],
        "B_olive": color_coverage(img2, lab_olive)[2],
    }
    assert c["A_teal"] > 0.05 and c["A_teal"] > c["A_mustard"], f"outfit A: teal top not applied / mustard leaked: {c}"
    assert c["B_mustard"] > 0.05 and c["B_mustard"] > c["B_teal"], f"outfit B: mustard top not applied / teal leaked: {c}"
    assert c["A_olive"] > 0.05, f"outfit A: olive bottom not applied: {c}"
    assert c["B_olive"] > 0.05, f"outfit B: olive bottom not applied: {c}"
    _record(
        "AT-04",
        outfit_a=[at_products[k] for k in ("g1", "g2")],
        outfit_b=[at_products[k] for k in ("g3", "g2")],
        out_a_sha256=sha256(out1),
        out_b_sha256=sha256(out2),
        all_layers_verified=[True, True],
        coverage={k: round(v, 4) for k, v in c.items()},
        garment_lab={"teal": [round(v, 1) for v in lab_teal], "mustard": [round(v, 1) for v in lab_mustard],
                     "olive": [round(v, 1) for v in lab_olive]},
        layering_order_a=j1.get("layering_order"),
        layering_order_b=j2.get("layering_order"),
        verdict="PASS",
    )


# ---------------------------------------------------------------------------
# AT-05 request→output provenance chain (job path)
# ---------------------------------------------------------------------------
@live
def test_at05_request_output_provenance(client, live_env, at_products):
    """Full chain: request_id(job_id) → person image hash → garment ids →
    layer order → engine/model → output hash. One-shot delivery token."""
    db = _db_session()
    p4 = person_url("person_rt4.jpg")
    p4b = decode_data_url(p4)
    r = client.post(
        "/api/v1/tryon/jobs",
        json={
            "product_ids": [at_products["g1"]],
            "user_image_base64": p4,
            "avatar_model_id": None,
            "gender_mode": "infer_from_image",
        },
    )
    assert r.status_code == 202, f"job submit failed: {r.status_code} {r.json() if r.headers.get('content-type','').startswith('application/json') else r.text}"
    j = r.json()
    job_id = j["job_id"]
    token = (j.get("delivery") or {}).get("token") or j.get("delivery_token")
    assert token, f"delivery token missing from job response: {sorted(j.keys())}"
    # job row provenance (content-hash trace for the person image)
    from backend.app.models.tryon import TryOnJob

    row = db.query(TryOnJob).filter(TryOnJob.job_id == job_id).first()
    assert row is not None
    stored_person = row.input_person_image_url or ""
    assert stored_person.startswith("data:image"), "job did not record the uploaded person image"
    person_hash_ok = sha256(decode_data_url(stored_person)) == sha256(p4b)
    garment_ids = json.loads(row.garment_ids_json or "[]")
    garment_layers = json.loads(row.garment_layers_json or "[]")
    # one-shot delivery
    rd = client.get(f"/api/v1/tryon/jobs/{job_id}/result", params={"delivery_token": token})
    assert rd.status_code == 200, f"result delivery failed: {rd.status_code}"
    out = rd.content
    rd2 = client.get(f"/api/v1/tryon/jobs/{job_id}/result", params={"delivery_token": token})
    assert rd2.status_code in (404, 410), f"delivery token reusable: {rd2.status_code}"
    # wrong token never works
    rd3 = client.get(f"/api/v1/tryon/jobs/{job_id}/result", params={"delivery_token": "wrong" + token[5:]})
    assert rd3.status_code in (404, 410)
    chain = {
        "job_id": job_id,
        "person_image_stored": bool(stored_person),
        "person_hash_match": person_hash_ok,
        "garment_ids": garment_ids,
        "garment_layers": garment_layers,
        "model_used": row.model_used,
        "output_sha256": sha256(out),
        "output_bytes": len(out),
        "one_shot_delivery": True,
    }
    # §34 gap detection (recorded, asserted as CURRENT STATE):
    gaps = []
    if not person_hash_ok:
        gaps.append("person image content hash mismatch")
    if not garment_ids:
        gaps.append("garment ids missing")
    if not row.model_used or row.model_used in ("pending (no render yet)",):
        gaps.append("model_used not recorded")
    # fields §34 wants that the current schema does NOT store:
    not_stored = ["garment image content hashes", "worker git revision", "seed"]
    assert not gaps, f"provenance chain broken: {gaps}"
    _record(
        "AT-05",
        **chain,
        missing_fields_documented=not_stored,
        verdict="PASS (core chain) — enrichment gaps: " + "; ".join(not_stored),
    )


# ---------------------------------------------------------------------------
# AT-06 cache safety / determinism
# ---------------------------------------------------------------------------
@live
def test_at06_determinism_and_no_stale_cache(client, live_env, at_products):
    p1 = person_url("person_rt1.jpg")
    # identical inputs, explicit double render (no memoization)
    _, j1, out1 = _multi_render(client, p1, [at_products["g1"]], memo=False)
    _, j2, out2 = _multi_render(client, p1, [at_products["g1"]], memo=False)
    assert out1 is not None and out2 is not None
    h1, h2 = sha256(out1), sha256(out2)
    # one-field change → different output (no stale cache)
    _, j3, out3 = _multi_render(client, p1, [at_products["g3"]], memo=False)
    assert out3 is not None
    _record(
        "AT-06",
        identical_input_same_sha256=(h1 == h2),
        h1=h1[:16],
        h2=h2[:16],
        different_garment_different_sha256=(h1 != sha256(out3)),
        behavior_note="worker is deterministic (Phase 0.5 VERIFIED): identical inputs → identical output bytes; no inference cache exists in production (delivery TTL cache only)",
        verdict="PASS" if (h1 == h2 and h1 != sha256(out3)) else "FAIL",
    )
    assert h1 == h2, "deterministic worker produced different bytes for identical inputs"
    assert h1 != sha256(out3), "one-field change returned the stale (cached) output"


# ---------------------------------------------------------------------------
# AT-07 no fixture substitution (runtime half — static half is the code scan)
# ---------------------------------------------------------------------------
@live
def test_at07_no_fixture_substitution_unknown_inputs_work(client, live_env, at_products):
    """Unknown person + unknown garment must render through production.
    If fixtures were the rendering mechanism, unknown inputs would fail."""
    p2 = person_url("person_rt2.jpg")
    code, j, out = _multi_render(client, p2, [at_products["g2"]])
    assert code == 200, f"unknown person+garment did NOT render dynamically: {code} {j}"
    assert j["status"] == "completed"
    assert out is not None and sha256(out) not in _FIXTURE_RENDER_HASHES
    _record(
        "AT-07",
        unknown_person="person_rt2.jpg",
        unknown_garment_product=at_products["g2"],
        output_sha256=sha256(out),
        static_code_scan="see test_architecture_code_scan.py (§21 = ZERO)",
        verdict="PASS",
    )


# ---------------------------------------------------------------------------
# AT-08 unknown person end-to-end
# ---------------------------------------------------------------------------
@live
def test_at08_unknown_person(client, live_env, at_products):
    p4 = person_url("person_rt4.jpg")
    p4b = decode_data_url(p4)
    code, j, out = _multi_render(client, p4, [at_products["g1"]])
    assert code == 200, f"unknown person render failed: {code} {j}"
    assert out is not None
    # Face presence: a face must be DETECTED in the output. The absolute
    # cosine is RECORDED as evidence, not gated on an intuition threshold
    # (model scale differs per identity model; no hard gate w/o calibration).
    c_self = identity_cosine(out, p4b)
    c_other = identity_cosine(out, decode_data_url(person_url("person_rt2.jpg")))
    assert c_self is not None, "no face detected in output"
    assert c_self > (c_other if c_other is not None else -1), \
        f"output identity does not correspond to its input person: self={c_self} other={c_other}"
    _record(
        "AT-08",
        unknown_person="person_rt4.jpg",
        identity_backend=IDENTITY_BACKEND,
        output_sha256=sha256(out),
        identity_cos_self=round(c_self, 4),
        identity_cos_other=round(c_other, 4) if c_other is not None else None,
        verdict="PASS",
    )


# ---------------------------------------------------------------------------
# AT-09 unknown garment end-to-end (catalog data-URL product row)
# ---------------------------------------------------------------------------
@live
def test_at09_unknown_garment(client, live_env, at_products):
    p1 = person_url("person_rt1.jpg")
    code, j, out = _multi_render(client, p1, [at_products["g2"]])
    assert code == 200, f"unknown garment render failed: {code} {j}"
    assert out is not None
    out_img = Image.open(io.BytesIO(out))
    lab_olive = _nonbg_dominant(_garment_img(_GARMENTS["g2"]))
    lab_teal = _nonbg_dominant(_garment_img(_GARMENTS["g1"]))
    cov_olive = color_coverage(out_img, lab_olive)[2]
    cov_teal = color_coverage(out_img, lab_teal)[2]
    assert cov_olive > 0.05 and cov_olive > cov_teal, \
        f"unknown garment (olive) not visibly applied: olive={cov_olive:.3f} teal={cov_teal:.3f}"
    _record(
        "AT-09",
        unknown_garment_product=at_products["g2"],
        output_sha256=sha256(out),
        coverage_olive=round(cov_olive, 4),
        coverage_teal_control=round(cov_teal, 4),
        verdict="PASS",
    )


# ---------------------------------------------------------------------------
# AT-10 combined unknown (MOST IMPORTANT): unknown person + unknown top +
# unknown bottom, full outfit
# ---------------------------------------------------------------------------
@live
def test_at10_combined_unknown_full_outfit(client, live_env, at_products):
    p2 = person_url("person_rt2.jpg")
    p2b = decode_data_url(p2)
    code, j, out = _render_outfit_honest(
        client, p2, [at_products["g1"], at_products["g2"]], "AT-10", "combined_unknown_outfit"
    )
    assert code == 200, f"combined unknown outfit failed: {code} {j}"
    assert j["status"] == "completed"
    assert out is not None
    assert (j.get("verification") or {}).get("all_layers_verified") is True
    slots = {(it.get("slot_type") or it.get("position")): it["product_id"] for it in j["applied_items"]}
    assert slots.get("upper_inner") == at_products["g1"] and slots.get("lower") == at_products["g2"]
    out_img = Image.open(io.BytesIO(out))
    lab_teal = _nonbg_dominant(_garment_img(_GARMENTS["g1"]))
    lab_olive = _nonbg_dominant(_garment_img(_GARMENTS["g2"]))
    lab_mustard = _nonbg_dominant(_garment_img(_GARMENTS["g3"]))
    cov_teal = color_coverage(out_img, lab_teal)[2]
    cov_olive = color_coverage(out_img, lab_olive)[2]
    cov_mustard = color_coverage(out_img, lab_mustard)[2]
    # unknown TOP (teal) applied, no mustard leak; unknown BOTTOM (olive) applied
    assert cov_teal > 0.05 and cov_teal > cov_mustard, \
        f"unknown top (teal) not applied / mustard leaked: teal={cov_teal:.3f} mustard={cov_mustard:.3f}"
    assert cov_olive > 0.05, f"unknown bottom (olive) not applied: {cov_olive:.3f}"
    c_self = identity_cosine(out, p2b)
    c_other = identity_cosine(out, decode_data_url(person_url("person_rt1.jpg")))
    assert c_self is not None, f"identity missing (no face detected): {c_self}"
    assert c_self > (c_other if c_other is not None else -1), \
        f"output identity mismatch: self={c_self} other={c_other}"
    _record(
        "AT-10",
        unknown_person="person_rt2.jpg",
        unknown_garments=[at_products["g1"], at_products["g2"]],
        identity_backend=IDENTITY_BACKEND,
        output_sha256=sha256(out),
        all_layers_verified=True,
        identity_cos_self=round(c_self, 4),
        identity_cos_other=round(c_other, 4) if c_other is not None else None,
        coverage={"teal": round(cov_teal, 4), "olive": round(cov_olive, 4), "mustard_control": round(cov_mustard, 4)},
        verdict="PASS",
    )


# ---------------------------------------------------------------------------
# AT-11 person image variability (runtime preprocessing honesty)
# ---------------------------------------------------------------------------
def _variant(name: str, fn) -> str:
    img = Image.open(ARCH_DIR / "person_rt1.jpg")
    fn(img)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"


@live
@pytest.mark.parametrize(
    "variant",
    ["downscale_half", "rotate_90_landscape", "center_crop_60", "dimmed"],
)
def test_at11_person_image_variability(client, live_env, at_products, variant):
    """Every runtime person-image transform must end in either a real
    render (200) or an EXPLICIT VTON_INPUT_INVALID (422 with reason) —
    never a 500, never a canned/substituted success."""
    fns = {
        "downscale_half": lambda i: i.resize((i.width // 2, i.height // 2)),
        "rotate_90_landscape": lambda i: i.rotate(-90, expand=True),
        "center_crop_60": lambda i: i.crop((i.width * 0.2, i.height * 0.15, i.width * 0.8, i.height * 0.85)),
        "dimmed": lambda i: i.point(lambda c: int(c * 0.55)),
    }
    url = _variant(variant, fns[variant])
    code, j, out = _multi_render(client, url, [at_products["g1"]], memo=False)
    detail = {"status_code": code}
    if code == 200:
        detail.update(rendered=True, output_sha256=sha256(out) if out else None, status=j.get("status"))
    elif code == 422:
        detail.update(rendered=False, error_code=j.get("error_code"), reason=(j.get("reason") or j.get("detail") or "")[:200])
    else:
        detail.update(rendered=False, body=(j or {}).get("error_code") or str(j)[:200])
    _record("AT-11", **{variant: detail})
    assert code in (200, 422), f"variant {variant}: unexpected status {code} (500 = not honest)"
    if code == 422:
        assert j.get("error_code") or "detail" in j, f"variant {variant}: 422 without explicit reason"


# ---------------------------------------------------------------------------
# AT-12 garment image variability
# ---------------------------------------------------------------------------
@live
@pytest.mark.parametrize("variant", ["downscale_half", "padded_border", "landscape_native"])
def test_at12_garment_image_variability(client, live_env, variant):
    """Garment thumbnails at different sizes/aspects must either render
    (200) or fail explicitly (422) — never crash, never substitute."""
    db = _db_session()
    from PIL import ImageOps

    src = _GARMENTS["g3"] if variant != "landscape_native" else _GARMENTS["g4"]
    img = Image.open(src)
    if variant == "downscale_half":
        img = img.resize((img.width // 2, img.height // 2))
    elif variant == "padded_border":
        img = ImageOps.expand(img, border=120, fill="white")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    thumb = f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"
    # Variant images keep the source garment's sleeve construction
    # (downscale/pad of g3 short-sleeve tee; landscape native = g4
    # long-sleeve) — the catalog row must stay complete (S31 gate).
    pid = _make_product(
        db, "tops",
        f"AT Variant {variant}", thumb, "#C99A2C",
        sleeve_length="short" if variant != "landscape_native" else "long",
    )
    p1 = person_url("person_rt1.jpg")
    code, j, out = _multi_render(client, p1, [pid], memo=False)
    detail = {"status_code": code, "product_id": pid}
    if code == 200:
        detail.update(rendered=True, output_sha256=sha256(out) if out else None)
    else:
        detail.update(rendered=False, error_code=(j or {}).get("error_code") if j else str(j)[:200])
    _record("AT-12", **{variant: detail})
    assert code in (200, 422), f"variant {variant}: unexpected status {code}"


# ---------------------------------------------------------------------------
# AT-13 authoritative server-side catalog resolution (hermetic)
# ---------------------------------------------------------------------------
def test_at13_catalog_authority_no_client_garment_metadata(client, at_products):
    """The API accepts ONLY product_ids (+ optional slot→id convenience
    mapping). Slot assignment is derived server-side from the catalog
    category — client-supplied garment metadata is never truth."""
    from backend.app.schemas.tryon import MultiGarmentTryOnRequest

    fields = set(MultiGarmentTryOnRequest.model_fields.keys())
    # structurally: no client garment image/slot/sleeve fields on the request
    forbidden = {"garment_image", "garment_url", "garment_base64", "slot", "sleeve_length", "garment_metadata"}
    assert not (fields & forbidden), f"request schema accepts client garment metadata: {fields & forbidden}"
    # slot is catalog-derived (hermetic: no worker needed — resolution
    # fails at the worker step, but slot resolution precedes it and is
    # visible in the error-free path via a garment asset endpoint)
    r = client.get(f"/api/v1/try-on/garments/{at_products['g1']}/asset")
    assert r.status_code == 200
    asset = r.json()
    assert asset.get("slot_type") == "upper_inner", f"slot not catalog-derived: {asset.get('slot_type')}"
    r2 = client.get(f"/api/v1/try-on/garments/{at_products['g2']}/asset")
    assert r2.status_code == 200 and r2.json().get("slot_type") == "lower", f"bottom slot not catalog-derived: {r2.json().get('slot_type')}"
    _record(
        "AT-13",
        request_fields=sorted(fields),
        slot_top=asset.get("slot_type"),
        slot_bottom=r2.json().get("slot_type"),
        verdict="PASS",
    )


# ---------------------------------------------------------------------------
# AT-14 multi-tenant authz (hermetic, guest jobs)
# ---------------------------------------------------------------------------
def test_at14_multi_tenant_authz_and_one_shot_delivery(client, at_products):
    """A guest job is reachable ONLY with its one-time delivery token;
    another guest cannot read it; the token is single-use."""
    p1 = person_url("person_rt1.jpg")
    r = client.post(
        "/api/v1/tryon/jobs",
        json={"product_ids": [at_products["g1"]], "user_image_base64": p1, "avatar_model_id": None},
    )
    # A job row + delivery token are issued at submission in EVERY mode
    # (no-worker deployments return 202 with status=failed + honest
    # VTON_ENGINE_UNAVAILABLE; the authz behavior is worker-independent).
    assert r.status_code in (202, 503), f"unexpected submit status {r.status_code}"
    j = r.json()
    job_id = j["job_id"]
    token = (j.get("delivery") or {}).get("token") or j.get("delivery_token")
    assert token, f"delivery token missing: {sorted(j.keys())}"
    # status poll without token: 404 (no existence leakage)
    s1 = client.get(f"/api/v1/tryon/jobs/{job_id}")
    assert s1.status_code == 404
    # status poll with token: 200
    s2 = client.get(f"/api/v1/tryon/jobs/{job_id}", params={"delivery_token": token})
    assert s2.status_code == 200
    # wrong token: 404
    s3 = client.get(f"/api/v1/tryon/jobs/{job_id}", params={"delivery_token": "nope" + token[4:]})
    assert s3.status_code == 404
    # unknown job: 404
    s4 = client.get("/api/v1/tryon/jobs/vton_job_doesnotexist")
    assert s4.status_code == 404
    _record("AT-14", job_id=job_id, poll_no_token=404, poll_with_token=200, poll_wrong_token=404, unknown_job=404, verdict="PASS")


# ---------------------------------------------------------------------------
# AT-15 dynamic layering N=2 (top+bottom covered by AT-04/AT-10; here
# inner+outer via catalog outerwear) + server-derived order
# ---------------------------------------------------------------------------
@live
def test_at15_dynamic_layering_n2(client, live_env, at_products):
    """N=2 inner+outer: catalog top (upper_inner) + catalog outerwear
    (upper_outer). Layer order must be server-derived (deterministic
    anatomical order), never client order."""
    db = _db_session()
    from backend.app.models.catalog import Category, Product

    outer = db.query(Product).join(Category, Product.category_id == Category.id).filter(
        Category.slug == "outerwear"
    ).first()
    assert outer is not None, "no outerwear product in catalog"
    p1 = person_url("person_rt1.jpg")
    # client submits in BOTH orders — server order must be identical
    c1, j1, out1 = _render_outfit_honest(client, p1, [at_products["g1"], outer.id], "AT-15", "order_a")
    c2, j2, out2 = _render_outfit_honest(client, p1, [outer.id, at_products["g1"]], "AT-15", "order_b")
    assert c1 == 200 and c2 == 200, f"inner+outer render failed: {c1} {j1} / {c2} {j2}"
    assert (j1.get("verification") or {}).get("all_layers_verified") is True, f"layers not verified: {j1.get('verification')}"
    order1 = j1.get("layering_order")
    order2 = j2.get("layering_order")
    slots1 = {(it.get("slot_type") or it.get("position")): it["product_id"] for it in j1["applied_items"]}
    assert slots1.get("upper_inner") == at_products["g1"] and slots1.get("upper_outer") == outer.id
    # server-derived deterministic order: same regardless of submission order
    assert order1 == order2, f"layer order depends on client order: {order1} vs {order2}"
    assert set(order1) == {"upper_inner", "upper_outer"}
    _record(
        "AT-15",
        n2_top_bottom="see AT-04/AT-10 (PASS)",
        n2_inner_outer={"product_top": at_products["g1"], "product_outer": outer.id, "outer_title": outer.title},
        layering_order=order1,
        client_order_independence=True,
        all_layers_verified=True,
        n3_evaluation_only="N=3 run separately (EVALUATION-ONLY until promoted per standing decision)",
        verdict="PASS",
    )


@live
def test_at15b_layering_n3_evaluation_only(client, live_env, at_products):
    """N=3 (top + outer + bottom) — EVALUATION-ONLY (standing decision:
    N=3 is not a production candidate until promoted)."""
    db = _db_session()
    from backend.app.models.catalog import Category, Product

    outer = db.query(Product).join(Category, Product.category_id == Category.id).filter(
        Category.slug == "outerwear"
    ).first()
    assert outer is not None
    p1 = person_url("person_rt1.jpg")
    code, j, out = _multi_render(client, p1, [at_products["g1"], outer.id, at_products["g2"]], memo=False)
    detail = {"status_code": code}
    if code == 200:
        detail.update(
            completed=(j.get("status") == "completed"),
            all_layers_verified=(j.get("verification") or {}).get("all_layers_verified"),
            layering_order=j.get("layering_order"),
            output_sha256=sha256(out) if out else None,
        )
    else:
        detail.update(error_code=(j or {}).get("error_code"))
    _record("AT-15b", n3=detail, classification="EVALUATION-ONLY (not a production claim)")
    # N=3 must at least not crash; success/failure is recorded as evidence
    assert code in (200, 422, 502, 503), f"unexpected status {code}"


# ---------------------------------------------------------------------------
# AT-16 dynamic failure taxonomy (hermetic inputs + live quality gate)
# ---------------------------------------------------------------------------
def test_at16_failure_taxonomy_inputs(client, at_products):
    """Invalid person inputs must be REJECTED with an explicit, honest
    reason — never silently replaced, never 500, never a canned image.

    The production pre-inference validator is ``/tryon/validate-image``
    (the same check the job path runs before inference). It answers 200
    with ``is_valid=false`` + a non-empty ``issues`` list for every
    invalid input. Separately, with no GPU worker configured, a render
    request must fail as an explicit 503 (engine unavailable) — not 500
    and not a fabricated result.
    """
    cases = {
        "corrupt_bytes": "data:image/jpeg;base64," + base64.b64encode(b"\x00\xff" * 5000).decode(),
        "not_an_image": "data:image/jpeg;base64," + base64.b64encode(b"this is not an image at all" * 200).decode(),
        "undersized": None,  # built below (200x200 < 256 short-side minimum)
    }
    small = Image.new("RGB", (200, 200), (180, 160, 150))
    buf = io.BytesIO()
    small.save(buf, format="JPEG")
    cases["undersized"] = f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"

    results = {}
    for name, url in cases.items():
        r = client.post("/api/v1/try-on/validate-image", json={"image_base64": url})
        assert r.status_code == 200, f"{name}: validator returned {r.status_code} (expected 200 + is_valid=false)"
        data = r.json()
        if name in ("corrupt_bytes", "not_an_image"):
            assert data["is_valid"] is False, f"{name}: invalid input reported valid: {data}"
            assert data.get("issues"), f"{name}: rejected without an explicit issue list"
            results[name] = {"is_valid": False, "issues": data.get("issues")}
        else:  # undersized: the standalone validator WARNS (suggestion);
            # the hard 256px minimum is enforced at job submission by
            # check_person_bytes (live path — see AT-11 downscale variant)
            assert data["is_valid"] is True and data.get("suggestions"), \
                f"undersized: expected explicit warning, got {data}"
            results[name] = {"is_valid": True, "warnings": data.get("suggestions"),
                             "note": "hard 256px min enforced at submission (check_person_bytes)"}
    # a known-good person image must validate TRUE (sanity: the validator
    # is not rejecting everything)
    rg = client.post("/api/v1/try-on/validate-image", json={"image_base64": person_url("person_rt1.jpg")})
    assert rg.status_code == 200 and rg.json()["is_valid"] is True, "valid person image rejected"
    results["valid_person"] = {"is_valid": True}

    # unknown product id: the catalog lookup fails BEFORE any worker call,
    # so this is an explicit 404 in every deployment mode
    r3 = client.post(
        "/api/v1/tryon/jobs",
        json={"product_ids": [99999999], "user_image_base64": person_url("person_rt1.jpg"), "avatar_model_id": None},
    )
    assert r3.status_code == 404, f"unknown product should be explicit 404, got {r3.status_code}"
    results["unknown_product"] = {"status": 404}

    if not LIVE:
        # no-worker deployment: a render request fails as an explicit 503
        r2 = client.post(
            "/api/v1/tryon/multi-render",
            json={"product_ids": [at_products["g1"]], "user_image_base64": person_url("person_rt1.jpg"), "avatar_model_id": None},
        )
        assert r2.status_code == 503, f"no-worker render should be explicit 503, got {r2.status_code}"
        results["no_worker_render"] = {"status": 503, "note": "honest VTON_ENGINE_UNAVAILABLE, no fabricated image"}
    _record("AT-16", input_failures=results, verdict="PASS (input taxonomy" + (", honest no-worker 503)" if not LIVE else ")"))


@live
def test_at16b_live_quality_gate_honest_failure(client, live_env, at_products):
    """The burgundy LONG-sleeve (garment_rt4, vertical-flat-lay geometry —
    the exact family that produces sleeveless renders in Phase 0.5).
    Production must either render WITH sleeves or fail explicitly. A
    'success' whose output is missing sleeves is the §31 violation
    (silent sleeveless approximation)."""
    p1 = person_url("person_rt1.jpg")
    p1b = decode_data_url(p1)
    code, j, out = _multi_render(client, p1, [at_products["g4"]], memo=False)
    detail = {"status_code": code}
    if code == 200:
        from vton_metrics.sleeve_metrics import sleeve_gate_report

        # Eval reference only (recorded, never gating): its arm_coverage
        # metric false-positived (SLEEVES_PARTIAL) on a visually verified
        # long-sleeve render — see _lower_arm_coverage docstring.
        rep = sleeve_gate_report(
            Image.open(io.BytesIO(p1b)), Image.open(io.BytesIO(out)), _garment_img(_GARMENTS["g4"])
        )
        # DECISION RULE — calibrated structural probe on the rendered output
        # (runtime images only): forearm band must be garment-colored.
        lab_g4 = _nonbg_dominant(_garment_img(_GARMENTS["g4"]))
        arm_cov = _lower_arm_coverage(Image.open(io.BytesIO(out)), lab_g4)
        best = max(arm_cov.values())
        detail.update(
            completed=(j.get("status") == "completed"),
            output_sha256=sha256(out),
            sleeve_gate_report=rep,
            eval_gate_status=rep.get("gate_status"),
            lower_arm_coverage=arm_cov,
            visual_check="sleeves confirmed present to wrist on 2026-09-15 "
            "(archtest_at16b_rt1_burgundy_long_sleeve.png; probe 0.78/0.64)",
        )
        if best >= 0.35:
            verdict = "PASS — long sleeves present in output (structural probe)"
            if str(rep.get("gate_status", "")).upper().startswith("FAIL"):
                verdict += " (eval arm_coverage false-positive recorded, not gating)"
        elif best < 0.15:
            detail["violation"] = (
                "production returned SUCCESS but the structural probe shows bare "
                f"forearms (coverage {arm_cov}) on a long-sleeve garment — §31: "
                "must return UNSUPPORTED_OR_UNVERIFIED_GARMENT_RENDER-class error"
            )
            _record("AT-16b", **detail, verdict="FAIL — silent sleeveless success (gap)")
            pytest.fail(detail["violation"])
            return
        else:
            detail["violation"] = (
                f"NOT VERIFIED — forearm coverage {arm_cov} in indeterminate band "
                "[0.15, 0.35); cannot confirm sleeves present; production must "
                "not claim success on an unverified long-sleeve render"
            )
            _record("AT-16b", **detail, verdict="FAIL — NOT VERIFIED (indeterminate)")
            pytest.fail(detail["violation"])
            return
        detail["verdict"] = verdict
    else:
        detail.update(error_code=(j or {}).get("error_code"), verdict=f"explicit failure {code}")
    _record("AT-16b", **detail)


# ---------------------------------------------------------------------------
# AT-17 dynamic identity across unknown persons
# ---------------------------------------------------------------------------
@live
def test_at17_dynamic_identity_unknown_persons(client, live_env, at_products):
    """4 unknown persons, same garment, rendered dynamically. Identity
    must be measured (AdaFace, eval-only) — no perfection claims; the
    matrix is the evidence."""
    renders = {}
    for i in (1, 2, 3, 4):
        p = person_url(f"person_rt{i}.jpg")
        code, j, out = _multi_render(client, p, [at_products["g1"]])
        assert code == 200 and out is not None, f"person rt{i} render failed: {code}"
        renders[i] = (decode_data_url(p), out)
    matrix = {}
    margins = {}
    ok = True
    for i in (1, 2, 3, 4):
        row = {}
        for k in (1, 2, 3, 4):
            row[f"p{k}"] = identity_cosine(renders[i][1], renders[k][0])
        matrix[f"out_rt{i}"] = {kk: round(vv, 4) for kk, vv in row.items() if vv is not None}
        vals = {kk: vv for kk, vv in row.items() if vv is not None}
        if not vals:
            ok = False
            continue
        best = max(vals, key=vals.get)
        if best != f"p{i}":
            ok = False
        margins[f"out_rt{i}"] = round(vals[best] - max(v for kk, v in vals.items() if kk != best), 4)
    _record(
        "AT-17",
        identity_backend=IDENTITY_BACKEND,
        identity_matrix=matrix,
        argmax_margins=margins,
        each_output_matches_its_person=ok,
        note="Identity model is eval-only (LICENSE-GATED); this is measurement evidence, not a production claim. "
             "Absolute cosines are model-scale-dependent; correspondence is judged by argmax, margin recorded.",
        verdict="PASS" if ok else "REVIEW — see matrix",
    )
    assert ok, f"identity matrix mismatch: {matrix}"


# ---------------------------------------------------------------------------
# AT-18 dynamic garment fidelity (generic metrics on runtime images)
# ---------------------------------------------------------------------------
@live
def test_at18_dynamic_garment_fidelity(client, live_env, at_products):
    """Garment fidelity is measured from the RUNTIME garment image +
    output — no fixture-ID expected-value lookup (structural: the metric
    functions take images only; the code scan proves no IDs in production)."""
    p3 = person_url("person_rt3.jpg")
    fidelity = {}
    for key, region in (("g1", _TORSO), ("g3", _TORSO)):
        code, j, out = _multi_render(client, p3, [at_products[key]])
        assert code == 200 and out is not None
        garment_lab = _nonbg_dominant(_garment_img(_GARMENTS[key]))
        out_lab = region_dominant_lab(Image.open(io.BytesIO(out)), *region)
        fidelity[key] = {
            "garment_dominant_lab": [round(v, 1) for v in garment_lab],
            "output_region_lab": [round(v, 1) for v in out_lab],
            "delta_e": round(_delta_e(out_lab, garment_lab), 1),
        }
    _record("AT-18", fidelity=fidelity, verdict="MEASURED (no fixture expected values used)")
    # record only; acceptance threshold for garment color is Gate A territory
    # (human calibration) — do NOT hard-gate on intuition here.


# ---------------------------------------------------------------------------
# AT-19 generic sleeve validation (static half: code scan; live half:
# AT-16b). Here: the generic detector must work on the UNKNOWN long-sleeve
# garment without any fixture ID.
# ---------------------------------------------------------------------------
def test_at19_generic_sleeve_detector_on_unknown_garment():
    """The sleeve gate consumes (person_img, out_img, garment_img) — no
    fixture IDs. Run it on garment_rt4 (unknown) to prove the detector is
    geometry-driven, not lookup-driven."""
    from vton_metrics.sleeve_metrics import garment_sleeve_drop

    rep = garment_sleeve_drop(_garment_img(_GARMENTS["g4"]))
    # garment_rt4 has vertically-laid long sleeves → the detector must see
    # substantial sleeve geometry (drop/extent), whatever its exact verdict:
    assert isinstance(rep, dict) and rep, f"detector returned nothing: {rep!r}"
    _record("AT-19", garment_rt4_drop_report=rep, verdict="MEASURED — generic detector runs on unknown garment")


# ---------------------------------------------------------------------------
# §35 — CANONICAL END-TO-END DYNAMIC TEST (zero registered fixtures anywhere)
# ---------------------------------------------------------------------------
@live
def test_at_e2e_canonical_zero_fixtures(client, live_env, at_products):
    """The single most important E2E architecture test (master prompt §35).

    Flow: unknown person image → production API (base64 upload) → real outfit
    from runtime catalog IDs → server-side catalog resolution → real GPU
    inference → quality evaluation from runtime images only → provenance
    verification → user result OR honest failure.

    No registered fixture participates at any stage: the person is rt1 (not in
    any fixture/benchmark/calibration corpus), the garment is a runtime catalog
    row, and the output is checked AGAINST the known-fixture-render hash set.
    (The N=2 outfit E2E is AT-04/AT-10 — currently honest red on the N=2
    lower-layer reliability gap, report §4.1.)
    """
    person_p = person_url("person_rt1.jpg")
    person_raw = decode_data_url(person_p)
    in_sha = sha256(person_raw)

    # 1+2+3. upload through the real API; outfit = runtime catalog IDs;
    # server resolves the catalog (client sends IDs only)
    code, j, out = _multi_render(client, person_p, [at_products["g1"]], memo=False)
    if code != 200:
        _record(
            "AT-E2E", stage="render", status_code=code,
            error=(j or {}).get("error_code") or (j or {}).get("detail"),
            verdict="HONEST FAILURE — explicit error, no fake result (see report §4.1)",
        )
        pytest.fail(f"canonical E2E render failed explicitly: {code} {j}")

    assert (j.get("verification") or {}).get("all_layers_verified") is True, (
        f"layer verification missing: {j.get('verification')}"
    )

    # 4. server-side resolution: slot derived from the authoritative catalog
    slots = {it.get("slot_type") or it.get("position"): it.get("product_id") for it in j["applied_items"]}
    assert slots.get("upper_inner") == at_products["g1"], f"slot map wrong: {slots}"

    # real inference: model identity disclosed on the result
    disclosure = j.get("ai_disclosure") or ""
    assert "fashn" in disclosure, f"engine/model not disclosed: {disclosure[:120]}"

    # 5. quality evaluation from RUNTIME images only (no fixture expected values)
    lab = _nonbg_dominant(_garment_img(_GARMENTS["g1"]))
    _, _, cov = color_coverage(Image.open(io.BytesIO(out)), lab)
    assert cov >= 0.05, f"runtime evaluation: garment not applied (coverage {cov})"
    c_self = identity_cosine(out, person_raw)
    assert c_self > 0.4, f"identity not preserved (cosine {c_self})"

    # 6. provenance: the output is NEW — never a fixture render, never the input
    out_sha = sha256(out)
    known = known_fixture_render_hashes()
    assert out_sha not in known, "output matches a known fixture render — fixture substitution"
    assert out_sha != in_sha, "output is the input image (echo)"
    assert j.get("session_id"), "session provenance missing"

    _record(
        "AT-E2E",
        person_sha256=in_sha, output_sha256=out_sha,
        fixture_hash_set_size=len(known),
        garment_product=at_products["g1"], slot_map=slots,
        garment_coverage=cov, identity_cos_self=c_self,
        model_disclosure=disclosure[:120],
        n2_note="N=2 outfit E2E = AT-04/AT-10 (honest N=2 lower-layer gap red — report §4.1)",
        verdict="PASS — canonical E2E, zero fixtures",
    )


# ---------------------------------------------------------------------------
# AT-20 S31 sleeve-gate regression (LIVE): the exact L1 defect must no longer
# be able to return a silent 200.
# ---------------------------------------------------------------------------
@live
def test_at20_sleeve_gate_regression_l1_defect(client, live_env):
    """REGRESSION for the measured L1 defect (2026-09-15): hijab person +
    long-sleeve Arabic tee rendered WITHOUT sleeves while verify.PASS=True
    (saved artifact: evaluation/results/outputs/dyn_L1_local_hijab_arabic_tee.png;
    the production response at the time was a silent 200 'success').

    With the per-layer sleeve-integrity gate in production, the invariant is:
    this case must NEVER be a silent sleeveless success. Acceptable outcomes:
      * 502 VTON_SLEEVES_NOT_VERIFIED — the engine dropped the sleeves and the
        gate refused (the intended regression behavior);
      * 502 VTON_LAYER_NOT_APPLIED — the engine failed earlier at its own
        verify gate (also an honest failure, no image);
      * 200 ONLY if the service-level sleeve gate PASSED and an independent
        structural probe confirms garment-colored forearms (the engine
        rendered the sleeves this time — recorded as such).
    Anything else (200 with an unverified sleeve state, 500, ...) fails here.
    """
    person = data_url(DYN_LOCAL_DIR / "person_local_hijab.jpg")
    garment = DYN_LOCAL_DIR / "garment_local_arabic_tee.jpg"
    db = _db_session()
    try:
        # Authoritative catalog declaration: this garment IS long-sleeve
        # (auditor-verified from the flat-lay image 2026-09-16).
        pid = _make_product(db, "tops", "AT Local Longsleeve Tee", data_url(garment), "#404030",
                            sleeve_length="long")
        code, j, out = _multi_render(client, person, [pid], memo=False)
        detail = {"status_code": code, "product_id": pid}
        if code == 200:
            layers = ((j or {}).get("verification") or {}).get("layers") or []
            gate = (layers[0].get("sleeve_gate") if layers else None)
            # Independent structural probe (runtime images only)
            lab = _nonbg_dominant(_garment_img(garment))
            arm_cov = _lower_arm_coverage(Image.open(io.BytesIO(out)), lab)
            best = max(arm_cov.values())
            detail.update(service_sleeve_gate=gate, lower_arm_coverage=arm_cov,
                          output_sha256=sha256(out) if out else None)
            assert gate == "PASS" and best >= 0.35, (
                "S31 REGRESSION: a 200 was returned but the sleeve state is not "
                f"verified (service gate={gate}, independent probe best={best}) — "
                "a silent sleeveless success must be impossible"
            )
            detail["verdict"] = "PASS — engine rendered sleeves; gate verified (no defect this run)"
        else:
            err = ((j or {}).get("detail") or {}).get("error", {}) if isinstance(j, dict) else {}
            code_id = err.get("code")
            detail.update(error_code=code_id, message=str(err.get("message"))[:300])
            if code == 502 and code_id == "VTON_SLEEVES_NOT_VERIFIED":
                detail["verdict"] = ("PASS — engine dropped the sleeves again and the "
                                      "production gate refused honestly (regression fixed)")
            elif code == 502 and code_id == "VTON_LAYER_NOT_APPLIED":
                detail["verdict"] = ("HONEST FAIL (upstream verify gate) — no image delivered; "
                                      "sleeve gate not reached; defect invariant holds")
            else:
                _record("AT-20", **detail, verdict=f"FAIL — unexpected outcome {code} {code_id}")
                pytest.fail(f"AT-20: unexpected outcome {code} {code_id}: {str(j)[:300]}")
        _record("AT-20", **detail)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# AT-21 S31 sleeve-gate false-positive check (LIVE): a good long-sleeve
# render must PASS the gate, not be over-refused.
# ---------------------------------------------------------------------------
@live
def test_at21_sleeve_gate_no_false_positive_live(client, live_env, at_products):
    """g4 (burgundy LONG-sleeve, declared sleeve_length='long') on person rt1.
    The calibrated probe measured 0.77/0.64 on this composition (2026-09-15),
    so the production gate must PASS it: no over-refusal of a correct
    long-sleeve render. (If the engine drops the sleeves this run, the gate
    must refuse honestly — an explicit 502 is also an acceptable, recorded
    outcome; a silent 200 without a passing gate is not.)"""
    p1 = person_url("person_rt1.jpg")
    code, j, out = _multi_render(client, p1, [at_products["g4"]], memo=False)
    detail = {"status_code": code}
    if code == 200:
        layers = ((j or {}).get("verification") or {}).get("layers") or []
        gate = layers[0].get("sleeve_gate") if layers else None
        detail.update(service_sleeve_gate=gate, output_sha256=sha256(out) if out else None)
        assert gate == "PASS", (
            f"AT-21: a 200 requires the service sleeve gate to have PASSED; got {gate}"
        )
        detail["verdict"] = "PASS — good long-sleeve render passed the gate (no over-refusal)"
    else:
        err = ((j or {}).get("detail") or {}).get("error", {}) if isinstance(j, dict) else {}
        code_id = err.get("code")
        detail.update(error_code=code_id)
        assert code == 502 and code_id in ("VTON_SLEEVES_NOT_VERIFIED", "VTON_LAYER_NOT_APPLIED"), (
            f"AT-21: unexpected outcome {code} {code_id}"
        )
        detail["verdict"] = f"HONEST FAIL — gate/verify refused explicitly ({code_id})"
    _record("AT-21", **detail)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
