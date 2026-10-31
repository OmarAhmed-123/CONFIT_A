"""The person input must be a FULL BODY, and the refusal must never guess.

Context (2026-10-25). Every bundled try-on avatar used to be a
head-and-shoulders portrait, and ``avatar_athletic_m`` — a face crop — was the
default ``avatar_model_id`` on every schema. A render on that input put a
garment on a face and still returned ``fit_confidence_score: 100`` with the
per-layer gate passing, because nothing on the person side ever asked whether
there was a body in the frame. A green gate on a meaningless image is worse
than an honest failure.

The contract these tests pin down:

1. The bundled avatars are full-body and are tagged as such, so the default
   path renders on a body.
2. A person reference we KNOW is a portrait is refused with an honest code —
   including the legacy portrait URLs, which a cached front-end bundle or an
   old API client can still send.
3. A person reference whose framing is unknown is NOT guessed at. This is the
   deliberate limit: measured on real images, a head-width heuristic rejected
   a legitimate cluttered-background full-body photo (37.7% "head width") and
   a skin-blob heuristic returned nothing at all for an obvious portrait, so
   any such gate would refuse real customers — disproportionately those
   photographing themselves at home, and those with darker skin tones. The
   guess is therefore not made here; uploads are guided in the UI instead.
4. Refusing on framing is ADDITIVE: the garment-side guard, the ghost-hands
   gate and ``assert_layer_applied`` are untouched.
"""

from __future__ import annotations

import base64
import io
import pathlib

import pytest
from PIL import Image

from backend.app.core.exceptions import ValidationDomainError
from backend.app.services import tryon_service as ts


# ── helpers ───────────────────────────────────────────────────────────────

def _data_url(size=(600, 900), colour=(120, 120, 120), grainy: bool = True) -> str:
    """A photo-shaped test image.

    Real photos do not compress to nothing; a flat fill does (9 KB for a 600x900
    grey rectangle, under the 10 KB floor ``check_person_bytes`` enforces).
    Grain keeps these fixtures on the same side of that floor as a real photo.
    """
    import numpy as np

    buf = io.BytesIO()
    img = Image.new("RGB", size, colour)
    if grainy:
        arr = np.asarray(img, dtype=np.int16)
        noise = np.random.default_rng(7).integers(-18, 19, arr.shape, dtype=np.int16)
        arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
        img = Image.fromarray(arr, "RGB")
    img.save(buf, "JPEG", quality=92)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


# ── 1. the bundled avatars are full-body, and the registry says so ────────

def test_every_bundled_avatar_is_tagged_full_body():
    assert ts.VTON_AVATARS, "the avatar registry must not be empty"
    for avatar_id in ts.VTON_AVATARS:
        assert ts.VTON_AVATAR_FRAMING[avatar_id] == ts.FRAMING_FULL_BODY, (
            f"{avatar_id} must render on a body, not a face"
        )


def test_every_bundled_avatar_asset_exists_on_disk():
    """A registry entry that points at a missing file is a render that fails
    at 3am; the files ship with the repo (backend/assets is not excluded from
    the serverless bundle by vercel.json)."""
    for avatar_id in ts.VTON_AVATARS:
        path = ts.avatar_asset_path(avatar_id)
        assert path is not None and path.exists(), f"{avatar_id}: {path} is missing"
        assert path.stat().st_size > 20_000, f"{avatar_id} asset looks truncated"


def test_avatar_assets_show_a_figure_filling_the_frame():
    """A full-length figure occupies most of the frame's height.

    This catches the failure that actually bit during development: an asset
    generated in landscape, where the person is a third of the frame. It is
    deliberately NOT presented as a portrait detector.

    Measured on a labelled set — old head-and-shoulders portraits and the new
    full-length assets — the obvious pixel signals do not separate the classes:
    a "top edge is narrow relative to the torso" ratio scored 0.44 for one
    portrait and 0.63 for one full-length asset, i.e. overlapping, and on a
    cluttered background a legitimate full-body photo scored 1.65 (it would be
    called a headshot). That is why the runtime framing decision is
    registry-based (``ensure_renderable_person_reference``) and why the
    contents of these four assets are established by eye, on the montage in the
    phase report, rather than by a threshold in this file.
    """
    import numpy as np

    for avatar_id in ts.VTON_AVATARS:
        img = Image.open(ts.avatar_asset_path(avatar_id)).convert("RGB")
        img.thumbnail((300, 500))
        rgb = np.asarray(img, dtype=np.float32)
        h, w, _ = rgb.shape
        k = max(2, int(w * 0.03))
        row_bg = np.median(np.concatenate([rgb[:, :k], rgb[:, -k:]], axis=1), axis=1)
        subj = np.linalg.norm(rgb - row_bg[:, None, :], axis=2) > 32.0
        subj &= (subj.mean(axis=1) < 0.85)[:, None]
        rows = np.where(subj.mean(axis=1) > 0.04)[0]
        assert len(rows) > 10, f"{avatar_id}: no subject found in the asset"
        span = (rows[-1] - rows[0] + 1) / h
        assert span > 0.80, (
            f"{avatar_id}: the figure spans only {span:.2f} of the frame height — "
            f"a full-length person should fill the frame, and the engine inherits "
            f"this framing"
        )


def test_the_default_avatar_id_is_a_full_body_avatar():
    """The schemas default to avatar_athletic_m; whatever that id resolves to
    must be full-body, or the default path renders on a face again."""
    from backend.app.schemas.tryon import MultiGarmentTryOnRequest, TryOnRequest

    for schema in (TryOnRequest, MultiGarmentTryOnRequest):
        default_id = schema.model_fields["avatar_model_id"].default
        assert default_id in ts.VTON_AVATARS, (
            f"{schema.__name__} defaults to {default_id!r}, which is not a bundled avatar"
        )
        assert ts.VTON_AVATAR_FRAMING[default_id] == ts.FRAMING_FULL_BODY


# ── 2. a reference we KNOW is a portrait is refused, honestly ─────────────

def test_a_known_portrait_reference_is_refused_with_an_honest_code():
    portrait = sorted(ts.VTON_RETIRED_PORTRAIT_REFERENCES)[0]
    with pytest.raises(ValidationDomainError) as exc:
        ts.resolve_person_reference(portrait, None, None)
    msg = str(exc.value)
    assert "VTON_PERSON_FRAMING_INVALID" in msg
    assert "full-body" in msg.lower() or "full body" in msg.lower()


def test_the_legacy_portrait_avatar_urls_are_still_refused():
    """The four Unsplash portraits the avatars used to point at. A cached
    front-end bundle or an older API client can still send them."""
    assert len(ts.VTON_RETIRED_PORTRAIT_REFERENCES) == 4
    for url in ts.VTON_RETIRED_PORTRAIT_REFERENCES:
        with pytest.raises(ValidationDomainError) as exc:
            ts.resolve_person_reference(url + "?w=600&auto=format&fit=crop&q=80", None, None)
        assert "VTON_PERSON_FRAMING_INVALID" in str(exc.value)


def test_a_portrait_tagged_avatar_id_is_refused(monkeypatch):
    """If anyone ever adds a portrait avatar, the registry refuses it rather
    than silently smearing a garment over a face."""
    monkeypatch.setitem(ts.VTON_AVATARS, "avatar_portrait_trap", ts.VTON_AVATARS["avatar_athletic_m"])
    monkeypatch.setitem(ts.VTON_AVATAR_FRAMING, "avatar_portrait_trap", ts.FRAMING_PORTRAIT)
    with pytest.raises(ValidationDomainError) as exc:
        ts.resolve_person_reference(None, None, "avatar_portrait_trap")
    assert "VTON_PERSON_FRAMING_INVALID" in str(exc.value)


def test_an_unknown_avatar_id_still_gets_the_existing_error():
    """The framing check must not change the existing contract for bad ids."""
    with pytest.raises(ValidationDomainError) as exc:
        ts.resolve_person_reference(None, None, "avatar_does_not_exist")
    msg = str(exc.value)
    assert "VTON_INPUT_INVALID" in msg
    assert "unknown avatar_model_id" in msg


# ── 3. accepted paths, and no guessing ───────────────────────────────────

def test_a_full_body_avatar_resolves_and_prepares_into_a_real_image():
    ref = ts.resolve_person_reference(None, None, "avatar_athletic_m")
    assert ref.startswith(ts.AVATAR_ASSET_SCHEME), (
        "an avatar must resolve to a repo-bundled asset reference, not a third-party URL"
    )
    data_url = ts.expand_avatar_asset(ref)
    assert data_url.startswith("data:image/")
    raw = base64.b64decode(data_url.split(",", 1)[1])
    ts.check_person_bytes(raw, "avatar")  # the existing size/aspect gate still applies
    assert Image.open(io.BytesIO(raw)).size[0] >= 256


def test_a_legitimate_full_body_upload_is_not_rejected():
    """Unknown framing means UNKNOWN, not guilty. A real customer photo on a
    cluttered background must pass the person checks untouched."""
    ref = ts.resolve_person_reference(_data_url(), None, None)
    assert ref.startswith("data:image/")
    ts.check_person_bytes(base64.b64decode(ref.split(",", 1)[1]), "upload")


def test_an_unknown_portrait_looking_upload_is_still_accepted():
    """Deliberate non-behaviour: a 2:3 upload that is in fact a bust is NOT
    guessed at. Documented limitation, surfaced in the UI copy, never a silent
    heuristic reject (see the module docstring for the measurements)."""
    bust = _data_url(size=(600, 900))
    assert ts.resolve_person_reference(bust, None, None) == bust


def test_an_uploaded_photo_still_wins_over_the_avatar():
    upload = _data_url(size=(700, 1000), colour=(90, 90, 90))
    assert ts.resolve_person_reference(upload, None, "avatar_athletic_m") == upload


def test_every_render_path_resolves_the_person_through_the_registry():
    """The framing check must sit on the ONE path every render takes.

    Four public render entry points exist (async job, sync render, multi-render
    and the session flow). Each resolves its person reference, so the check
    belongs in that one function; a second resolution path — an entry point
    reading ``VTON_AVATARS`` directly — would be a hole. Pinned with the AST so
    a refactor that inlines the lookup fails here.
    """
    import ast

    tree = ast.parse(pathlib.Path(ts.__file__).read_text())
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "resolve_person_reference"
    ]
    # Three render entry points resolve their own person reference:
    # create_and_enqueue_vton_job, execute_multi_garment_tryon (which
    # execute_tryon delegates to) and execute_animated_tryon. If a fourth
    # render path is ever added without resolving here, this count changes and
    # the new path must be checked by hand.
    assert len(calls) == 3, (
        f"expected exactly the 3 render entry points to resolve through "
        f"resolve_person_reference, found {len(calls)} call sites"
    )

    # VTON_AVATARS may only be read inside the resolver and its helpers.
    allowed = {"resolve_person_reference", "avatar_asset_path", "ensure_renderable_person_reference"}
    offenders = []
    for func in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        if func.name in allowed:
            continue
        for node in ast.walk(func):
            if isinstance(node, ast.Name) and node.id == "VTON_AVATARS":
                offenders.append(func.name)
    assert not offenders, (
        f"VTON_AVATARS read outside the registry resolver, in: {sorted(set(offenders))}"
    )


# ── 4. asset quality invariants, learned by rendering ────────────────────
#
# Both of these were found by running real renders, not by reading the model
# card, and both change the output a customer sees.

def test_avatar_assets_are_portrait_orientation():
    """The model inherits the person image's aspect ratio.

    Measured: a 1376x768 (landscape) person image returned a 576x321 render in
    which the figure is a third of the frame height — technically a passing
    layer gate, useless as a try-on. The bundled assets are therefore portrait,
    close to the model's native 2:3 (576x864).
    """
    for avatar_id in ts.VTON_AVATARS:
        w, h = Image.open(ts.avatar_asset_path(avatar_id)).size
        assert h > w * 1.3, (
            f"{avatar_id} is {w}x{h}: the engine inherits the person image's "
            f"aspect, so a landscape avatar renders a tiny figure"
        )
        assert 0.55 < w / h < 0.80, (
            f"{avatar_id} aspect {w / h:.2f} is far from the model's native 2:3 "
            f"(0.67); the render is letterboxed against it"
        )


def test_avatar_base_garments_contrast_with_the_catalogue():
    """An avatar's own clothing must differ from the garment being applied.

    Measured, and this is the failure mode that matters: an avatar in black
    trousers rendered against navy trousers produced
    ``pixel_change=0.21%, color_shift=0.0014`` — the engine barely touched the
    image, and the per-layer gate correctly refused with
    ``VTON_LAYER_NOT_APPLIED``. That is the gate doing its job, but it makes
    the demo path fail for a reason the customer cannot act on.

    The bundled people therefore wear a light neutral base (open floor: a
    white tee is also wrong, because the catalogue's white Oxford then has
    nothing to change). This pins the light base; the *contrast* property is
    demonstrated end to end by the renders in the phase report, not asserted
    here against a live GPU.
    """
    import numpy as np

    for avatar_id in ts.VTON_AVATARS:
        img = Image.open(ts.avatar_asset_path(avatar_id)).convert("RGB")
        img.thumbnail((300, 500))
        rgb = np.asarray(img, dtype=np.float32)
        h, w, _ = rgb.shape
        # the torso band: roughly 28-45% down the frame for a full-length figure
        torso = rgb[int(h * 0.28): int(h * 0.45), int(w * 0.35): int(w * 0.65)]
        mean_luma = float(torso.mean())
        assert mean_luma > 120, (
            f"{avatar_id}: torso mean luminance {mean_luma:.0f} is a dark base "
            f"garment; dark catalogue colours render almost no visible change"
        )
