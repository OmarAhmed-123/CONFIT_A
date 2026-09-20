"""Regression tests for the S31 production sleeve-integrity gate.

The defect under test (measured 2026-09-15, LOCAL DYNAMIC case L1): the FASHN
engine rendered a LONG-sleeve garment WITHOUT its sleeves and still returned
``verify.PASS=True``; the production chain reported a silent success. The
engine's verify gate is structurally blind to dropped sleeves, so the fix is a
separate, per-layer sleeve-integrity gate (``vton_sleeve_gate``) driven by
authoritative catalog metadata + a calibrated CHANGED garment-color forearm
probe: a band pixel counts as sleeve evidence only when the output is
garment-colored (ΔE ≤ 40 from the garment's dominant color) AND has changed
relative to the layer input (ΔE(output, input) > 20).

Two measured calibration events shaped the probe (both 2026-09-16):
  1. absolute -> differential: a plain absolute-color probe FALSE-PASSED the
     real L1 artifact because the person's own tan skirt sits at ΔE≈38 (< 40)
     from the dark-olive garment and occupies part of the forearm band.
  2. differential -> change (v2.2, current): the differential probe
     ("garment-colored in output but not already garment-colored in input")
     FALSE-REFUSED correctly rendered, fully-sleeved, engine-verified DARK
     garments, because dark trousers/background at the band are already
     within ΔE 40 of a dark garment reference and kill the newness signal:
       live contract C-07 (seed blazer on person rt4): 0.2110 -> REFUSE on a
         good render (engine verify PASS);
       E-1 standalone blazer (raw person rt2): 0.0366/0.1077 -> REFUSE on a
         render with clearly present long sleeves.
     The change condition (ΔE(output, input) > 20) removes input-side
     contamination of ANY color family — dark trousers, the L1 tan skirt —
     while still counting a real applied sleeve.

Change-probe v2.2 measurements (best-arm of the two bands):
  L1 defect (sleeves dropped):   0.0102 / 0.0274 -> REFUSE
  E-1 blazer (sleeves present):  0.3524          -> PASS (thinnest case)
  C-07 blazer (sleeves present): 0.6022          -> PASS
  AT-16b (sleeves present):      0.4725          -> PASS
  L2 dress (sleeves present):    0.9436          -> PASS

These tests are HERMETIC (no GPU worker, no network): synthetic images for
the decision table (including the same-family contamination case), plus
replays of the five real artifacts when present on disk.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from backend.app.services import vton_sleeve_gate as sg
from backend.app.services.vton_sleeve_gate import (
    SleevesNotVerifiedError,
    evaluate_layer_sleeves,
    evaluate_sleeves_sync,
)

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "evaluation" / "results" / "outputs"
ARCH = REPO / "evaluation" / "archtest_inputs"
DYN = REPO / "evaluation" / "dyninputs" / "local"

# A clearly chromatic, non-skin garment color (burgundy, same family as g4).
BURGUNDY = (110, 34, 51)
# A realistic mid skin tone for "bare forearm" negatives.
SKIN = (224, 178, 140)
# The L1 contamination color: a tan the wearer's own skirt occupies in the
# forearm band region (ΔE ≈ 38 from the dark-olive garment — inside the
# probe radius, the exact false-PASS mechanism measured 2026-09-16).
TAN = (199, 178, 145)
# Dark-olive garment (the L1 garment family).
OLIVE = (64, 64, 32)
# Pure white background: skipped by garment_dominant_lab (> 235 rule).
WHITE = (250, 250, 250)

# Forearm band boxes (must match the production probe).
BANDS = ((0.28, 0.46), (0.52, 0.70))
BAND_Y = (0.40, 0.55)
TORSO_Y = (0.28, 0.40)


def _b64_data_url(img: Image.Image, fmt: str = "PNG") -> str:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format=fmt)
    import base64

    return f"data:image/{fmt.lower()};base64," + base64.b64encode(buf.getvalue()).decode()


def _paint(img, x_frac0, x_frac1, y_frac0, y_frac1, color):
    px = img.load()
    w, h = img.size
    for y in range(int(h * y_frac0), int(h * y_frac1)):
        for x in range(int(w * x_frac0), int(w * x_frac1)):
            px[x, y] = color


def _garment_img(color=BURGUNDY) -> Image.Image:
    """Flat-lay garment: a colored block on a pure-white background so the
    dominant-color estimate lands on the garment color."""
    img = Image.new("RGB", (300, 300), WHITE)
    _paint(img, 0.2, 0.8, 0.2, 0.8, color)
    return img


def _person_img(band_color=SKIN, torso_color=(90, 90, 90), w: int = 360, h: int = 640) -> Image.Image:
    """Layer INPUT: a person photo with bare (or clothing-covered) forearms.
    ``band_color`` = what the forearm band region shows BEFORE this layer."""
    img = Image.new("RGB", (w, h), WHITE)
    _paint(img, 0.30, 0.70, *TORSO_Y, torso_color)
    for (fx0, fx1) in BANDS:
        _paint(img, fx0, fx1, *BAND_Y, band_color)
    return img


def _render_img(forearm_color, torso_color=BURGUNDY, band_extra=None,
                w: int = 360, h: int = 640) -> Image.Image:
    """Layer OUTPUT: torso garment-colored; forearm bands ``forearm_color``
    (plus optional extra patch, e.g. the wearer's skirt in the band region)."""
    img = Image.new("RGB", (w, h), WHITE)
    _paint(img, 0.30, 0.70, *TORSO_Y, torso_color)
    for (fx0, fx1) in BANDS:
        _paint(img, fx0, fx1, *BAND_Y, forearm_color)
    if band_extra:
        x0, x1, color = band_extra  # patch on the right band (x 0.60-0.70)
        _paint(img, x0, x1, *BAND_Y, color)
    return img


def _sync(slot, sleeve, out, inp, garment_color=BURGUNDY):
    return evaluate_sleeves_sync(
        slot_type=slot, sleeve_length=sleeve,
        output_img=out, input_img=inp, garment_img=_garment_img(garment_color),
    )


# ---------------------------------------------------------------------------
# Decision table (pure sync core) — deterministic, no I/O
# ---------------------------------------------------------------------------
def test_gate_pass_long_sleeves_present():
    """Person with bare forearms + long-sleeve garment rendered with sleeves
    -> NEW burgundy in both bands -> PASS."""
    d = _sync("upper_inner", "long",
              _render_img(BURGUNDY), _person_img(SKIN))
    assert d["status"] == "PASS", d
    assert max(d["coverage"].values()) >= sg.FOREARM_PASS_THRESHOLD


def test_gate_refuse_long_sleeves_dropped_bare_forearms():
    """THE DEFECT: long-sleeve garment, forearms remain bare (skin) ->
    no NEW garment color -> REFUSE."""
    d = _sync("upper_inner", "long",
              _render_img(SKIN), _person_img(SKIN))
    assert d["status"] == "REFUSE", d
    assert max(d["coverage"].values()) < sg.FOREARM_PASS_THRESHOLD


def test_gate_refuse_same_family_contamination_not_new():
    """Calibration event 1 (L1): the wearer's own tan clothing occupies the
    forearm band and is within ΔE 40 of the dark-olive garment. Under the
    change probe it is garment-colored but UNCHANGED relative to the input
    (ΔE(output, input) ≈ 0) -> not sleeve evidence -> REFUSE (the absolute
    probe false-passed this: right band 0.4992)."""
    person = _person_img(TAN, torso_color=TAN)
    out = _render_img(SKIN, torso_color=OLIVE, band_extra=(0.60, 0.70, TAN))
    d = _sync("upper_inner", "long", out, person, garment_color=OLIVE)
    assert d["status"] == "REFUSE", (
        f"same-family contamination must not count as an applied sleeve; got {d}"
    )
    assert max(d["coverage"].values()) < sg.FOREARM_PASS_THRESHOLD


def test_gate_short_sleeve_is_na_not_refused():
    d = _sync("upper_inner", "short", _render_img(SKIN), _person_img(SKIN))
    assert d["status"] == "N/A", d


def test_gate_no_sleeve_is_na():
    d = _sync("upper_outer", "none", _render_img(SKIN), _person_img(SKIN))
    assert d["status"] == "N/A", d


def test_gate_lower_slot_is_na_even_if_declared_long():
    d = _sync("lower", "long", _render_img(SKIN), _person_img(SKIN))
    assert d["status"] == "N/A", d


def test_gate_footwear_and_accessory_are_na():
    for slot in ("footwear", "accessory"):
        d = _sync(slot, "long", _render_img(SKIN), _person_img(SKIN))
        assert d["status"] == "N/A", (slot, d)


def test_gate_undeclared_upper_garment_is_refused_never_guess():
    """AT-19: an upper garment with no sleeve declaration is NOT assumed
    short-sleeve; the gate refuses rather than guess."""
    d = _sync("upper_inner", None, _render_img(BURGUNDY), _person_img(SKIN))
    assert d["status"] == "REFUSE", d


def test_gate_indeterminate_band_is_refused_failsafe():
    """A best-arm reading in [0.15, 0.35) is indeterminate -> REFUSE."""
    # One band: ~28% NEW burgundy (partial sleeve coverage -> indeterminate),
    # the other band bare. 0.055/0.18 of the band width = ~0.28 coverage.
    out = _render_img(SKIN)
    px = out.load()
    w, h = out.size
    for y in range(int(h * BAND_Y[0]), int(h * BAND_Y[1])):
        for x in range(int(w * 0.28), int(w * 0.335)):
            px[x, y] = BURGUNDY
    d = _sync("upper_inner", "long", out, _person_img(SKIN))
    best = max(d["coverage"].values())
    assert 0.05 < best < sg.FOREARM_PASS_THRESHOLD, (best, d)
    assert d["status"] == "REFUSE", (best, d)


# ---------------------------------------------------------------------------
# v2.2 change-probe calibration cases (Phase 2, 2026-09-16) — generic
# synthetic compositions stressing the dark-garment / dark-input failure
# mode discovered on the C-07 and E-1 artifacts. No fixture/ID references.
# ---------------------------------------------------------------------------
# A dark trouser / background color of a DIFFERENT family from the garment
# (deep navy vs burgundy garment): ΔE > 20 from the applied sleeve color.
DARK_TROUSER = (24, 28, 44)
# A dark color in the SAME family as the garment (near-black vs burgundy):
# within ΔE 20 of the sleeve color — the worst case for the change condition.
SAME_FAMILY_DARK = (44, 14, 20)


def test_gate_pass_dark_garment_over_dark_trousers():
    """C-07/E-1 failure mode, fixed side: a dark garment applied over a person
    with dark (non-garment-family) trousers. The output is garment-colored AND
    changed at the pixel -> sleeve evidence -> PASS. (The differential v2.1
    probe false-refused exactly this: input already 'garment-colored'.)"""
    d = _sync("upper_outer", "long",
              _render_img(BURGUNDY), _person_img(DARK_TROUSER))
    assert d["status"] == "PASS", d
    assert max(d["coverage"].values()) >= sg.FOREARM_PASS_THRESHOLD


def test_gate_refuse_dark_trousers_unchanged_no_garment():
    """Unchanged dark region resembling the garment family: the input band is
    dark trousers of a similar tone and the output is UNCHANGED there (no
    garment applied). Garment-colored-ish but ΔE(output, input) ≈ 0 -> no
    sleeve evidence -> REFUSE. This is the hypothesis test: changed-vs-input
    must distinguish an applied sleeve from an unchanged dark region."""
    # Output == input at the bands (no application); torso changes to garment.
    out = _render_img(DARK_TROUSER, torso_color=BURGUNDY)
    person = _person_img(DARK_TROUSER, torso_color=(90, 90, 90))
    d = _sync("upper_outer", "long", out, person)
    assert d["status"] == "REFUSE", d
    assert max(d["coverage"].values()) < sg.FOREARM_FAIL_THRESHOLD


def test_gate_refuse_same_family_dark_unchanged():
    """Worst case: input band is a same-family dark color (near-black) and the
    output is unchanged there; the garment is burgundy (ΔE < 40 from the
    near-black, so 'garment-colored'), but ΔE(output, input) < 20 (same
    family) -> not sleeve evidence -> REFUSE."""
    out = _render_img(SAME_FAMILY_DARK, torso_color=BURGUNDY)
    person = _person_img(SAME_FAMILY_DARK, torso_color=(90, 90, 90))
    d = _sync("upper_outer", "long", out, person)
    assert d["status"] == "REFUSE", d
    assert max(d["coverage"].values()) < sg.FOREARM_PASS_THRESHOLD


def test_gate_refuse_partial_sleeve_drop():
    """Partial drop: only ~30% of one band carries the applied sleeve
    (changed garment color), the rest remains bare skin (unchanged) ->
    best-arm coverage lands in [0.15, 0.35) -> REFUSE (NOT_VERIFIED),
    never a silent partial success."""
    out = _render_img(SKIN)
    px = out.load()
    w, h = out.size
    for y in range(int(h * BAND_Y[0]), int(h * BAND_Y[1])):
        for x in range(int(w * 0.28), int(w * 0.335)):  # 0.055/0.18 ≈ 0.31
            px[x, y] = BURGUNDY
    d = _sync("upper_inner", "long", out, _person_img(SKIN))
    best = max(d["coverage"].values())
    assert sg.FOREARM_FAIL_THRESHOLD <= best < sg.FOREARM_PASS_THRESHOLD, (best, d)
    assert d["status"] == "REFUSE", (best, d)


def test_gate_pass_low_margin_positive():
    """Low-margin positive: ~0.37 best-arm coverage (just above the 0.35
    line, the E-1 composition class) -> PASS. Pins the thin-margin side of
    the boundary so a future change cannot silently move it.

    The band's reduced coverage comes from BACKGROUND bleed into the fixed
    band (the measured E-1/C-07 mechanism — the band is wider than the
    arm), NOT from exposed forearms: both arms carry sleeve fabric to the
    wrist and no skin sits in the outer band. (The pre-v2.4 version of this
    test modeled the low coverage as bare forearms; v2.4 correctly refuses
    that image — a one-arm render — via the any-skin channel.)"""
    out = _render_img(SKIN)
    px = out.load()
    w, h = out.size
    for y in range(int(h * BAND_Y[0]), int(h * BAND_Y[1])):
        # both bands get the sleeve (burgundy)...
        for x in range(int(w * 0.28), int(w * 0.46)):
            px[x, y] = BURGUNDY
        for x in range(int(w * 0.52), int(w * 0.70)):
            px[x, y] = BURGUNDY
        # ...then background (white, not garment-colored) bleeds into most of
        # each band -> best-arm coverage ~0.3636 (same grid reading as the
        # original measured 0.28-0.34 patch), both arms still fully sleeved
        for x in range(int(w * 0.34), int(w * 0.46)):
            px[x, y] = WHITE
        for x in range(int(w * 0.58), int(w * 0.70)):
            px[x, y] = WHITE
    d = _sync("upper_inner", "long", out, _person_img(SKIN))
    best = max(d["coverage"].values())
    assert sg.FOREARM_PASS_THRESHOLD <= best < sg.FOREARM_PASS_THRESHOLD + 0.1, (best, d)
    assert d["status"] == "PASS", (best, d)
    assert max(a["any_skin_outer"] for a in d["anatomy"].values()) < sg.ANATOMY_ANY_SKIN_REFUSE


def test_gate_refuse_low_margin_negative():
    """Low-margin negative: ~0.10 best-arm coverage (just below the 0.15
    fail line — a near-miss application) -> REFUSE (sleeves absent)."""
    out = _render_img(SKIN)
    px = out.load()
    w, h = out.size
    for y in range(int(h * BAND_Y[0]), int(h * BAND_Y[1])):
        for x in range(int(w * 0.28), int(w * 0.30)):  # 0.02/0.18 ≈ 0.11
            px[x, y] = BURGUNDY
    d = _sync("upper_inner", "long", out, _person_img(SKIN))
    best = max(d["coverage"].values())
    assert best < sg.FOREARM_FAIL_THRESHOLD, (best, d)
    assert d["status"] == "REFUSE", (best, d)


def test_gate_one_piece_dress_slot_runs_probe():
    """A dress slot with declared long sleeves runs the same probe as an
    upper slot (one-piece long-sleeve dress = L2 composition class)."""
    d = _sync("dress", "long", _render_img(BURGUNDY), _person_img(SKIN))
    assert d["status"] == "PASS", d
    d2 = _sync("dress", "long", _render_img(SKIN), _person_img(SKIN))
    assert d2["status"] == "REFUSE", d2


def test_gate_white_garment_blind_spot_refuses():
    """A near-white garment on a white background has no measurable dominant
    color -> REFUSE (safe direction), never a silent pass."""
    d = _sync("upper_inner", "long", _render_img(WHITE), _person_img(SKIN),
              garment_color=WHITE)
    assert d["status"] == "REFUSE", d


# ---------------------------------------------------------------------------
# Async entry point (decodes data URLs, raises on REFUSE)
# ---------------------------------------------------------------------------
def test_async_entry_pass_returns_decision():
    import asyncio

    d = asyncio.run(evaluate_layer_sleeves(
        slot_type="upper_inner", sleeve_length="long",
        output_data_url=_b64_data_url(_render_img(BURGUNDY)),
        input_data_url=_b64_data_url(_person_img(SKIN)),
        garment_ref=_b64_data_url(_garment_img()),
        product_id=1, layer=1,
    ))
    assert d["status"] == "PASS", d


def test_async_entry_refuse_raises_canonical_code():
    import asyncio

    with pytest.raises(SleevesNotVerifiedError) as ei:
        asyncio.run(evaluate_layer_sleeves(
            slot_type="upper_inner", sleeve_length="long",
            output_data_url=_b64_data_url(_render_img(SKIN)),
            input_data_url=_b64_data_url(_person_img(SKIN)),
            garment_ref=_b64_data_url(_garment_img()),
            product_id=1, layer=1,
        ))
    assert "VTON_SLEEVES_NOT_VERIFIED" in str(ei.value)


def test_async_entry_short_sleeve_never_touches_images():
    """N/A paths must not require decodable images (fast path)."""
    import asyncio

    d = asyncio.run(evaluate_layer_sleeves(
        slot_type="upper_inner", sleeve_length="short",
        output_data_url="data:image/png;base64,AAAA",
        input_data_url="data:image/png;base64,AAAA",
        garment_ref="data:image/png;base64,AAAA",
        product_id=1, layer=1,
    ))
    assert d["status"] == "N/A", d


def test_async_entry_undeclared_upper_refuses_without_images():
    import asyncio

    with pytest.raises(SleevesNotVerifiedError):
        asyncio.run(evaluate_layer_sleeves(
            slot_type="upper_outer", sleeve_length=None,
            output_data_url="data:image/png;base64,AAAA",
            input_data_url="data:image/png;base64,AAAA",
            garment_ref="data:image/png;base64,AAAA",
            product_id=1, layer=1,
        ))


def test_async_entry_missing_garment_refuses_long():
    """A long-sleeve garment whose image the gate cannot obtain must REFUSE
    (fail-safe), not silently pass."""
    import asyncio

    with pytest.raises(SleevesNotVerifiedError):
        asyncio.run(evaluate_layer_sleeves(
            slot_type="upper_inner", sleeve_length="long",
            output_data_url=_b64_data_url(_render_img(BURGUNDY)),
            input_data_url=_b64_data_url(_person_img(SKIN)),
            garment_ref="",  # unavailable
            product_id=1, layer=1,
        ))


# ---------------------------------------------------------------------------
# v2.3 anatomical integrity channels (Phase 5, 2026-09-19)
#
# The coverage probe alone FALSE-PASSED the measured class-E artifact
# (dropped sleeves; white torso / short-sleeve region carried the coverage:
# best-arm 0.7062). Two monotone-safe anatomy channels now run on the
# coverage-PASS path:
#   new-skin  (arm-side band: output skin-colored AND changed vs input)
#   wrist-reach (arm-side wrist zone: changed garment-color fraction)
# They can only add REFUSE, never create a false positive.
# ---------------------------------------------------------------------------
# A dark garment that covered the forearm in the layer input (the class-E
# abaya family): clearly not skin, not burgundy-family.
DARK_COVER = (42, 42, 50)


def _render_class_e(forearm_inner_frac=0.35, w: int = 360, h: int = 640) -> Image.Image:
    """Class-E composition, generic: torso garment-colored; on one band the
    INNER (torso-edge) part is garment-colored (carries the coverage) and the
    OUTER (arm-side) part is BARE SKIN that was garment-covered in the input
    (newly exposed skin)."""
    img = _render_img(SKIN, torso_color=BURGUNDY)
    px = img.load()
    # left band (image right): x 0.52-0.70; outer = 0.583-0.70 stays SKIN,
    # inner = 0.52-0.583 becomes BURGUNDY (torso edge) -> coverage ~0.35+.
    for y in range(int(h * BAND_Y[0]), int(h * BAND_Y[1])):
        for x in range(int(w * 0.52), int(w * 0.583)):
            px[x, y] = BURGUNDY
    return img


def test_v23_refuse_new_skin_class_e_mechanism():
    """THE CLASS-E FP, hermetic: coverage >= 0.35 carried by the torso edge
    while the arm side shows newly exposed bare skin (input was garment-
    covered). The new-skin channel must REFUSE even though the old coverage
    probe PASSed (0.7062 on the real artifact)."""
    d = _sync("upper_inner", "long", _render_class_e(), _person_img(DARK_COVER))
    best = max(d["coverage"].values())
    assert best >= sg.FOREARM_PASS_THRESHOLD, (best, d)
    assert d["status"] == "REFUSE", (
        f"class-E mechanism (newly exposed skin at the arm side) must be "
        f"refused; got {d}"
    )
    assert d.get("anatomy"), "anatomy channels must run on the PASS path"


def test_v23_refuse_wrist_reach_partial_drop_over_garment():
    """Partial drop over a garment-covered input, hermetic: the sleeve color
    covers the torso + upper band but STOPS mid-band; the wrist zone shows
    the UNCHANGED input garment (not skin, not the sleeve). Coverage stays
    high (torso/upper arm), wrist-reach ~ 0 -> REFUSE."""
    img = Image.new("RGB", (360, 640), WHITE)
    _paint(img, 0.30, 0.70, *TORSO_Y, BURGUNDY)
    for (fx0, fx1) in BANDS:
        _paint(img, fx0, fx1, *BAND_Y, BURGUNDY)          # full band burgundy
        _paint(img, fx0, fx1, 0.49, 0.55, (245, 245, 240))  # wrist zone: input garment
    d = _sync("upper_inner", "long", img, _person_img((245, 245, 240)))
    best = max(d["coverage"].values())
    assert best >= sg.FOREARM_PASS_THRESHOLD, (best, d)
    assert d["status"] == "REFUSE", (
        f"partial drop (no sleeve at the wrist) must be refused; got {d}"
    )
    assert max(a["wrist_reach"] for a in d["anatomy"].values()) < sg.ANATOMY_WRIST_REACH_REFUSE


def test_v23_pass_unchanged_for_good_render():
    """A good long-sleeve render (sleeve reaches the wrist, no new skin)
    still PASSES with the anatomy channels active — the channels must not
    over-refuse the common case."""
    d = _sync("upper_inner", "long", _render_img(BURGUNDY), _person_img(DARK_COVER))
    assert d["status"] == "PASS", d
    assert max(a["new_skin_outer"] for a in d["anatomy"].values()) < sg.ANATOMY_NEW_SKIN_REFUSE
    assert max(a["wrist_reach"] for a in d["anatomy"].values()) >= sg.ANATOMY_WRIST_REACH_REFUSE
    # v2.4: a fully sleeved render leaves no skin in the outer band either.
    assert max(a["any_skin_outer"] for a in d["anatomy"].values()) < sg.ANATOMY_ANY_SKIN_REFUSE


def test_v24_refuse_asymmetric_drop_on_exposed_arm_input():
    """Phase 6 P1-B measured failure class (measured 2026-09-19 on the
    cal_02 base — input wears a tank top, arms exposed; real composite:
    evaluation/results/p6_sleeve_adversarial/adv_onearm_full.png):

    the layer INPUT already exposes both forearms (band color = skin); the
    render keeps the LEFT sleeve fully to the wrist but DROPS the right one,
    showing the person's own unchanged skin on that arm.

    Every v2.3 channel is max-aggregated across arms and the dropped arm's
    skin is NOT new vs the input (measured new_skin_outer = exactly 0.0 on
    that arm), so v2.3 FALSE-PASSED the real composite (S1 best-arm
    0.4608, new-skin best-arm 0.0022, wrist-reach best-arm 0.2422 — all
    carried by the intact arm). The v2.4 any-skin channel (skin in the
    outer band whether or not new; measured 0.2350 on the real composite)
    must REFUSE this render."""
    inp = _person_img(SKIN, torso_color=(90, 90, 90))  # both forearms exposed
    out = Image.new("RGB", (360, 640), WHITE)
    _paint(out, 0.30, 0.70, *TORSO_Y, BURGUNDY)
    _paint(out, 0.28, 0.46, *BAND_Y, SKIN)        # right band: dropped -> OLD skin
    _paint(out, 0.52, 0.70, *BAND_Y, BURGUNDY)    # left band: intact sleeve to wrist
    d = _sync("upper_inner", "long", out, inp)
    # Pin the mechanism: the intact arm carries every v2.3 max-arm channel...
    assert max(d["coverage"].values()) >= sg.FOREARM_PASS_THRESHOLD, (d, )
    assert max(a["new_skin_outer"] for a in d["anatomy"].values()) < sg.ANATOMY_NEW_SKIN_REFUSE, d
    assert max(a["wrist_reach"] for a in d["anatomy"].values()) >= sg.ANATOMY_WRIST_REACH_REFUSE, d
    # ...and the dropped arm's outer band is skin in the output (old or new).
    assert max(a["any_skin_outer"] for a in d["anatomy"].values()) >= sg.ANATOMY_ANY_SKIN_REFUSE, d
    assert d["status"] == "REFUSE", d
    assert "any-skin" in d["reason"], d["reason"]


def test_v23_refuse_bare_forearm_drop_over_dark_cover():
    """A full drop over a garment-covered input: the band shows bare skin
    that was covered in the input (new skin) AND no wrist reach. Must
    REFUSE (coverage of the bare skin against the burgundy reference is low
    -> likely refused by coverage already; the anatomy channels are the
    backstop when torso-edge coverage carries the reading)."""
    d = _sync("upper_inner", "long", _render_class_e(), _person_img(DARK_COVER))
    assert d["status"] == "REFUSE", d


def test_v23_skin_window_excludes_catalog_garment_families():
    """The calibrated skin window (L* 25-85 / a* 7-25 / b* 7-31) must NOT
    classify the measured catalog garment colors as skin. The a* 25 cap is the
    discriminating axis: the warmest measured FOREARM is a* 18.1 (1.38x below),
    the closest measured garment (dark-rust/terracotta) is a* 29.3 (1.17x
    above). A rust long sleeve on a dark input must not read as 'new skin'."""
    garments = {
        "dark-rust": (160, 82, 45),        # a* 29.3 -> above the a* 25 cap
        "rendered-rust": (206, 96, 73),    # a* 41.9 -> above the cap
        "terracotta": (194, 92, 52),       # a* 38.1 -> above the cap
        "burgundy": (110, 34, 51),         # a* 35.0 -> above the cap
        "brick-red": (178, 34, 34),        # a* 55.9 -> above the cap
        "mustard": (218, 165, 32),         # b* 68.8 -> above the b* 31 cap
        "purple": (123, 45, 78),           # b* -2.6 -> below the b* 7 floor
        "beige": (216, 200, 168),          # a* 0.5 -> below the a* 7 floor
        "olive": (62, 87, 46),             # a* -17.9 -> below the floor
        "navy": (30, 41, 59),              # a* 1.1 -> below the floor
        "black": (25, 25, 25),             # L* 8.8 -> below the L* 25 floor
        "white": (250, 250, 250),          # L* 98.3 -> above the L* 85 cap
    }
    for name, rgb in garments.items():
        assert not sg._is_skin_lab(sg._rgb_to_lab(rgb)), f"{name} ({rgb}) is a garment, not skin"
    # Cohort skin tones (fair -> deep, measured reference tones) MUST be skin.
    for skin in ((235, 200, 170), (224, 178, 140), (190, 132, 95), (140, 86, 58), (96, 58, 40)):
        assert sg._is_skin_lab(sg._rgb_to_lab(skin)), f"{skin} cohort skin tone must be in window"
    # The class-E exposed forearm (the anatomical target, measured a* 9.6-18.1)
    # MUST be skin, so the new-skin channel catches the drop.
    assert sg._is_skin_lab(sg._rgb_to_lab((150, 108, 84))), "class-E forearm must be in window"


# ---------------------------------------------------------------------------
# Real-artifact replay (only when the measured outputs are on disk)
# ---------------------------------------------------------------------------
_L1_OUT = OUT / "dyn_L1_local_hijab_arabic_tee.png"
_L1_PERSON = DYN / "person_local_hijab.jpg"
_L1_GARMENT = DYN / "garment_local_arabic_tee.jpg"
_AT16B_OUT = OUT / "archtest_at16b_rt1_burgundy_long_sleeve.png"
_AT16B_PERSON = ARCH / "person_rt1.jpg"
_AT16B_GARMENT = ARCH / "garment_rt4.jpg"
# Dark-garment over-refusal regression artifacts (calibration event 2,
# 2026-09-16): the differential v2.1 probe refused both of these correctly
# rendered, fully-sleeved, engine-verified dark blazers.
_E1_OUT = OUT / "e1_blazer_L1_raw_rt2.png"
_E1_PERSON = ARCH / "person_rt2.jpg"
_E1_GARMENT = REPO / "evaluation" / "dyninputs" / "global" / "garment_global_logo_blazer.jpg"
_C07_OUT = OUT / "e1_rt4_blazer_p1.png"
_C07_PERSON = ARCH / "person_rt4.jpg"
_C07_GARMENT = ARCH / "garment_seed_p1_blazer.jpg"


@pytest.mark.skipif(not (_L1_OUT.exists() and _L1_PERSON.exists() and _L1_GARMENT.exists()),
                    reason="L1 defect artifact not present on disk")
def test_replay_l1_defect_artifact_now_refused():
    """The exact L1 artifact (sleeves dropped, verify.PASS=True at the time)
    must now be REFUSED by the gate when the garment is declared long-sleeve.
    The layer input is the person photo (layer 1)."""
    out_img = Image.open(_L1_OUT).convert("RGB")
    in_img = Image.open(_L1_PERSON).convert("RGB")
    d = evaluate_sleeves_sync(
        slot_type="upper_inner", sleeve_length="long",
        output_img=out_img, input_img=in_img,
        garment_img=Image.open(_L1_GARMENT).convert("RGB"),
    )
    assert d["status"] == "REFUSE", (
        f"L1 defect artifact must be refused by the gate; got {d['status']} "
        f"coverage={d.get('coverage')}"
    )


@pytest.mark.skipif(not (_AT16B_OUT.exists() and _AT16B_PERSON.exists() and _AT16B_GARMENT.exists()),
                    reason="AT-16b good-render artifact not present on disk")
def test_replay_at16b_good_long_sleeve_artifact_passes():
    """The AT-16b artifact (long sleeves confirmed present, visually verified
    to the wrist 2026-09-15) must PASS — the gate must not false-positive on
    a good long-sleeve render."""
    out_img = Image.open(_AT16B_OUT).convert("RGB")
    in_img = Image.open(_AT16B_PERSON).convert("RGB")
    d = evaluate_sleeves_sync(
        slot_type="upper_inner", sleeve_length="long",
        output_img=out_img, input_img=in_img,
        garment_img=Image.open(_AT16B_GARMENT).convert("RGB"),
    )
    assert d["status"] == "PASS", (
        f"AT-16b good long-sleeve render must pass; got {d['status']} "
        f"coverage={d.get('coverage')}"
    )


@pytest.mark.skipif(not (_E1_OUT.exists() and _E1_PERSON.exists() and _E1_GARMENT.exists()),
                    reason="E-1 dark-blazer artifact not present on disk")
def test_replay_e1_dark_blazer_not_overrefused():
    """OVER-REFUSAL REGRESSION (calibration event 2, 2026-09-16): the E-1
    standalone blazer on raw person rt2 is a correctly rendered, fully-
    sleeved, engine-verified DARK garment. The differential v2.1 probe read
    0.0366/0.1077 (REFUSE) because the person's dark trousers/background at
    the forearm band are within ΔE 40 of the dark-navy reference and kill the
    newness signal. The change probe (garment-colored AND changed vs input)
    measures 0.3524 best-arm -> must PASS (the thinnest measured case)."""
    out_img = Image.open(_E1_OUT).convert("RGB")
    in_img = Image.open(_E1_PERSON).convert("RGB")
    d = evaluate_sleeves_sync(
        slot_type="upper_inner", sleeve_length="long",
        output_img=out_img, input_img=in_img,
        garment_img=Image.open(_E1_GARMENT).convert("RGB"),
    )
    assert d["status"] == "PASS", (
        f"E-1 dark blazer is a good fully-sleeved render and must NOT be "
        f"over-refused; got {d['status']} coverage={d.get('coverage')}"
    )


@pytest.mark.skipif(not (_C07_OUT.exists() and _C07_PERSON.exists() and _C07_GARMENT.exists()),
                    reason="C-07 seed-blazer artifact not present on disk")
def test_replay_c07_seed_blazer_not_overrefused():
    """OVER-REFUSAL REGRESSION (calibration event 2, 2026-09-16): the C-07
    seed blazer on person rt4 is a correctly rendered, fully-sleeved, engine-
    verified DARK garment (the live contract C-07 render). The differential
    v2.1 probe read 0.2110 (NOT_VERIFIED -> REFUSE) on this good render. The
    change probe measures 0.6022 best-arm -> must PASS."""
    out_img = Image.open(_C07_OUT).convert("RGB")
    in_img = Image.open(_C07_PERSON).convert("RGB")
    d = evaluate_sleeves_sync(
        slot_type="upper_outer", sleeve_length="long",
        output_img=out_img, input_img=in_img,
        garment_img=Image.open(_C07_GARMENT).convert("RGB"),
    )
    assert d["status"] == "PASS", (
        f"C-07 seed blazer is a good fully-sleeved render and must NOT be "
        f"over-refused; got {d['status']} coverage={d.get('coverage')}"
    )


# ---------------------------------------------------------------------------
# Phase 5 (2026-09-19) — the measured class-E FP + P0-C calibration replays.
# Labels are AGENT VISUAL INSPECTION (NOT HUMAN GROUND TRUTH) per the audit
# report; the artifacts are committed under evaluation/results/.
# ---------------------------------------------------------------------------
RES = REPO / "evaluation" / "results"
_CLASS_E_OUT = RES / "p4_fresh_batch" / "p4_j_arabic2_L1.png"
_CLASS_E_IN = RES / "p4_fresh_batch" / "p4_j_arabic2_L1_input.png"
_CLASS_E_GAR = RES / "p4_fresh_batch" / "p4_j_arabic2_L1_garment.png"
_SYNTH_PARTIAL = RES / "p4_fresh_batch" / "p0c_synth_partial_krust_L1"
def _sp(suffix: str) -> Path:
    return _SYNTH_PARTIAL.with_name(_SYNTH_PARTIAL.name + suffix)
_TP_REPLAYS = (
    (RES / "calibration_v22" / "cal_01_L1", "upper_inner"),
    (RES / "calibration_v22" / "cal_05_L1", "upper_inner"),
    (RES / "phase3_sleeve_batch" / "sc_rust_H_L1", "upper_inner"),
    (RES / "phase3_sleeve_batch" / "sc_rust_I_L1", "upper_inner"),
    (RES / "p4_fresh_batch" / "p4_k_rust_L1", "upper_inner"),
    (RES / "p4_fresh_batch" / "p4_k_black_L1", "upper_inner"),
    (RES / "p0c_sleeve_calibration" / "p0c_d_gray_L1", "upper_inner"),
    (RES / "p0c_sleeve_calibration" / "p0c_l_black_L1", "upper_inner"),
)


@pytest.mark.skipif(not (_CLASS_E_OUT.exists() and _CLASS_E_IN.exists() and _CLASS_E_GAR.exists()),
                    reason="class-E measured artifact not present on disk")
def test_replay_class_e_false_pass_now_refused():
    """HARD SAFETY PROPERTY (Phase 5 P0-D): the measured class-E artifact —
    a visibly sleeveless long-sleeve render that the v2.2 coverage probe
    FALSE-PASSED (best-arm 0.7062; the white torso / short-sleeve region
    carried the coverage while the exposed forearm showed bare skin,
    new-skin 0.2992) — MUST be REFUSED by the v2.3 gate."""
    d = evaluate_sleeves_sync(
        slot_type="upper_inner", sleeve_length="long",
        output_img=Image.open(_CLASS_E_OUT).convert("RGB"),
        input_img=Image.open(_CLASS_E_IN).convert("RGB"),
        garment_img=Image.open(_CLASS_E_GAR).convert("RGB"),
    )
    assert d["status"] == "REFUSE", (
        f"class-E artifact (sleeves visibly missing) must never be delivered "
        f"as an ordinary successful long-sleeve result; got {d}"
    )
    assert max(a["new_skin_outer"] for a in d["anatomy"].values()) >= sg.ANATOMY_NEW_SKIN_REFUSE


@pytest.mark.skipif(not _sp("_L1.png").exists(),
                    reason="synthetic partial-drop artifact not present on disk")
def test_replay_synthetic_partial_drop_refused():
    """Independently constructed drop (hermetic composite: the sleeve ends at
    mid-forearm, the input garment shows below; torso/upper-arm coverage
    0.4007): the wrist-reach channel must REFUSE it."""
    d = evaluate_sleeves_sync(
        slot_type="upper_inner", sleeve_length="long",
        output_img=Image.open(_sp("_L1.png")).convert("RGB"),
        input_img=Image.open(_sp("_L1_input.png")).convert("RGB"),
        garment_img=Image.open(_sp("_L1_garment.png")).convert("RGB"),
    )
    assert d["status"] == "REFUSE", d
    assert max(a["wrist_reach"] for a in d["anatomy"].values()) < sg.ANATOMY_WRIST_REACH_REFUSE


# Phase 6 P1-B measured false-pass composites (2026-09-19): the cal_02 base
# (input = white tank top, arms exposed) with the person's right sleeve
# dropped (elbow-length / fully bare). v2.3 FALSE-PASSED both (max-arm
# aggregation + old-skin blindness of the new-skin channel); the v2.4
# any-skin channel must REFUSE them.
_P1B_ADV = RES / "p6_sleeve_adversarial"
_P1B_IN = RES / "calibration_v22" / "cal_02_L1_input.png"
_P1B_GAR = RES / "calibration_v22" / "cal_02_L1_garment.png"


@pytest.mark.skipif(not ((_P1B_ADV / "adv_onearm_full.png").exists()
                         and _P1B_IN.exists() and _P1B_GAR.exists()),
                    reason="P1-B adversarial composite not present on disk")
def test_replay_p1b_asymmetric_drop_composite_refused():
    """THE P1-B measured false pass (Phase 6, 2026-09-19): the person's
    right arm fully bare from shoulder to hand, left sleeve intact, input
    tank top already exposed the arm (so the exposed skin is NOT new vs the
    input — v2.3's new-skin channel read exactly 0.0 on the dropped arm and
    the intact arm carried every max-aggregated channel). A visibly
    incomplete long-sleeve render must never be delivered."""
    for name in ("adv_onearm.png", "adv_onearm_full.png"):
        d = evaluate_sleeves_sync(
            slot_type="upper_inner", sleeve_length="long",
            output_img=Image.open(_P1B_ADV / name).convert("RGB"),
            input_img=Image.open(_P1B_IN).convert("RGB"),
            garment_img=Image.open(_P1B_GAR).convert("RGB"),
        )
        assert d["status"] == "REFUSE", (name, d)
        assert max(a["any_skin_outer"] for a in d["anatomy"].values()) >= sg.ANATOMY_ANY_SKIN_REFUSE, (name, d)
        assert "any-skin" in d["reason"], (name, d["reason"])


@pytest.mark.parametrize("artifact,slot", _TP_REPLAYS,
                         ids=[str(a.parent.name) + "/" + a.name.split("_L1")[0] for a, _ in _TP_REPLAYS])
@pytest.mark.skipif(not any(a.with_name(a.name + ".png").exists() for a, _ in _TP_REPLAYS),
                    reason="P0-C calibration artifacts not present on disk")
def test_replay_measured_true_positives_not_overrefused(artifact, slot):
    """The 16-artifact measured TP population must not be over-refused by the
    v2.3 anatomy channels (sampled here; the full 50-row decision table is
    asserted in evaluation/tests/test_sleeve_v23_matrix.py)."""
    out_p = artifact.with_name(artifact.name + ".png")
    if not out_p.exists():
        pytest.skip(f"{out_p} not on disk")
    d = evaluate_sleeves_sync(
        slot_type=slot, sleeve_length="long",
        output_img=Image.open(out_p).convert("RGB"),
        input_img=Image.open(artifact.with_name(artifact.name + "_input.png")).convert("RGB"),
        garment_img=Image.open(artifact.with_name(artifact.name + "_garment.png")).convert("RGB"),
    )
    assert d["status"] == "PASS", (
        f"measured true positive {artifact.name} must not be over-refused; "
        f"got {d}"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
