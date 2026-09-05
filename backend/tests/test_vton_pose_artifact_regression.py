"""Pose-preserving full-outfit VTON — duplicate-anatomy / pose-transfer regression.

The reported production artifact: a person image with a specific pose (hands
on waist / arms crossed) + a selected outfit renders back with **extra
hands/arms** or with the garment/model photo's pose instead of the uploaded
person's pose.

These tests use DETERMINISTIC committed fixtures (see
``backend/tests/fixtures/vton/ATTRIBUTION.md``) and exercise the artifact
detection harness itself:

* clean pair (person, same pose re-encoded)      -> PASS, no signal
* synthesized duplicate hand (2 -> 3 hands)      -> FAIL, EXTRA_HANDS
* mirrored body (pose transferred from a wrong
  reference)                                     -> FAIL, POSE_SWAP / drift

They pin that the harness reliably detects the exact reported failure mode,
so a regression in the detection or the pipeline's artifact profile is
caught. Per the directive, fixtures are for automated regression ONLY —
final production acceptance runs the same harness on a real production
render plus a documented human review (see closure report §Visual).
"""

import base64
import io
import inspect

import pytest

from PIL import Image

from backend.tests import vton_artifact_check as vac

FIX = "backend/tests/fixtures/vton"


@pytest.fixture(scope="module")
def two_hands():
    return Image.open(f"{FIX}/person_two_hands.jpg").convert("RGB")


@pytest.fixture(scope="module")
def arms_crossed():
    return Image.open(f"{FIX}/person_arms_crossed.jpg").convert("RGB")


# ── 1. the harness detects the duplicate-hand artifact ────────────────────
def _synthesize_extra_hand(person: Image.Image) -> Image.Image:
    """Deterministically paste a second copy of a detected hand into an
    empty area — simulating the 'extra hand' compositing artifact."""
    count, wrists = vac.count_hands(person)
    assert count >= 1, "fixture must yield at least one detectable hand"
    w, h = person.size
    cx, cy = int(wrists[0][0] * w), int(wrists[0][1] * h)
    bw, bh = int(w * 0.22), int(h * 0.22)
    crop = person.crop((max(0, cx - bw // 2), max(0, cy - bh // 2),
                        min(w, cx + bw // 2), min(h, cy + bh // 2)))
    out = person.copy()
    mirror = crop.transpose(Image.FLIP_LEFT_RIGHT)
    tx, ty = int(w * 0.80), int(h * 0.18)
    out.paste(mirror, (tx - mirror.width // 2, ty - mirror.height // 2))
    return out


def test_harness_detects_duplicate_hand(two_hands):
    report = vac.compare_person_and_result(two_hands, _synthesize_extra_hand(two_hands))
    assert report.person_hands == 2
    assert report.result_hands >= 3, report.to_dict()
    assert report.hand_count_delta >= 1
    assert report.verdict == "FAIL", report.to_dict()
    assert any("EXTRA_HANDS" in r for r in report.reasons)


def test_harness_clean_pair_passes(arms_crossed):
    buf = io.BytesIO()
    arms_crossed.save(buf, format="PNG")
    buf.seek(0)
    clean = Image.open(buf).convert("RGB")

    report = vac.compare_person_and_result(arms_crossed, clean)
    assert report.person_hands == report.result_hands
    assert report.pose_detected_person and report.pose_detected_result
    assert report.pose_drift is not None and report.pose_drift < 0.02
    assert report.wrist_swapped is False
    assert report.verdict == "PASS", report.to_dict()


def test_harness_detects_pose_transfer():
    """A mirrored body = the pose came from a different reference (the
    garment/model photo), not the uploaded person. The hands-on-waist
    fixture is the exact pose category from the 2026-09-05 directive;
    mirroring it produces a large, unambiguous body-pose drift."""
    person = Image.open(f"{FIX}/person_hands_on_waist.jpg").convert("RGB")
    mirrored = person.transpose(Image.FLIP_LEFT_RIGHT)
    report = vac.compare_person_and_result(person, mirrored)
    assert report.pose_drift is not None and report.pose_drift >= vac.DRIFT_FAIL, report.to_dict()
    assert report.verdict == "FAIL", report.to_dict()
    assert any("POSE_DRIFT_FAIL" in r or "POSE_SWAP" in r for r in report.reasons)


def test_hands_on_waist_clean_pair_preserved():
    """The directive's acceptance sample pose (hands on waist) on a clean
    (person, same-pose) pair must PASS with a stable hand count (2) and near
    zero drift."""
    person = Image.open(f"{FIX}/person_hands_on_waist.jpg").convert("RGB")
    buf = io.BytesIO()
    person.save(buf, format="PNG")
    buf.seek(0)
    clean = Image.open(buf).convert("RGB")
    report = vac.compare_person_and_result(person, clean)
    assert report.person_hands == 2 and report.result_hands == 2
    assert report.pose_drift is not None and report.pose_drift < 0.02
    assert report.verdict == "PASS", report.to_dict()


def test_harness_rejects_garbage_input():
    with pytest.raises(ValueError):
        vac.load_image("definitely not an image " * 20)
    with pytest.raises(ValueError):
        vac.load_image(b"\x00\x01\x02\x03")


# ── 2. person/pose reference separation (structural invariant) ────────────
def test_person_reference_never_derived_from_garment_assets():
    """The person image sent to the worker must be built ONLY from the
    user-supplied person reference (URL/base64) or the explicit avatar
    asset — never from a product/garment asset field."""
    import re

    from backend.app.services import tryon_service

    src = inspect.getsource(tryon_service)
    for method in ("create_and_enqueue_vton_job", "execute_multi_garment_tryon"):
        m = re.search(
            rf"def {method}\(.*?\n(?=    async def |    def |    # =)",
            src, re.S,
        )
        assert m, method
        body = m.group(0)
        # The effective person image expression must reference only the
        # user-provided fields / avatar assets — no product attribute.
        eff = re.search(r"effective_(?:input_)?image\s*=\s*(.+?)(?:\n\s{8}\S)", body, re.S)
        assert eff, f"effective person-image assignment not found in {method}"
        expr = eff.group(1)
        for forbidden in ("thumbnail_url", "garment_image", "p.image", "product.image"):
            assert forbidden not in expr, (
                f"{method}: person reference derived from a garment asset: {expr!r}"
            )


def test_worker_payload_keeps_person_and_garments_separate():
    """The worker contract carries the person image and the garments list in
    distinct fields; garment entries must not reuse the person image."""
    from backend.app.services.tryon_service import TryOnService

    # Structural: the process payload builds person_image and garments from
    # different sources.
    src = inspect.getsource(TryOnService._call_gpu_worker)
    assert '"user_image_base64_or_url": person_image' in src
    assert '"garments": garments' in src
