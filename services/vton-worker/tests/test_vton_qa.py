"""CPU unit tests for the post-render QA gate (ghost-hands remediation).

Synthetic 240x320 scenes: gray background, dark torso, skin-tone head.
No GPU, no torch, no weights.
"""
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vton_qa import (  # noqa: E402
    QA_SEED_LADDER,
    background_drift,
    detect_new_skin_blobs,
    face_drift,
    paste_back_identity,
    qa_gate,
    skin_mask,
)

H, W = 320, 240
SKIN = (210, 170, 140)   # inside YCrCb skin bounds
NAVY = (27, 31, 59)
GRAY = (120, 120, 120)
DARK = (30, 30, 30)


def _scene(torso=NAVY, hands=False) -> np.ndarray:
    img = np.zeros((H, W, 3), np.uint8)
    img[:] = GRAY
    # head (skin) in the face band
    yy, xx = np.ogrid[:H, :W]
    head = ((yy - 50) ** 2 + (xx - W // 2) ** 2) <= 28**2
    img[head] = SKIN
    # torso from 0.38h down
    y0 = int(0.38 * H)
    img[y0:, W // 4 : 3 * W // 4] = torso
    if hands:
        # two skin blobs at the waist (the ghost-hands artifact)
        for cx in (W // 2 - 30, W // 2 + 30):
            blob = ((yy - (y0 + 40)) ** 2) // 4 + (xx - cx) ** 2 <= 16**2
            img[blob] = SKIN
    return img


def test_skin_mask_detects_skin_only():
    img = _scene()
    m = skin_mask(img)
    assert m[50, W // 2]                      # head pixel = skin
    assert not m[H - 10, W // 2]              # torso not skin
    assert not m[5, 5]                        # background not skin


def test_clean_render_passes_gate():
    person = _scene(torso=DARK)
    rendered = _scene(torso=NAVY)             # garment applied, nothing invented
    qa = qa_gate(person, rendered)
    assert qa["qa_PASS"] is True
    assert qa["ghost_skin_blobs"] == 0
    assert qa["qa_reasons"] == []


def test_ghost_hands_fail_gate():
    person = _scene(torso=DARK)
    rendered = _scene(torso=NAVY, hands=True)  # invented skin at the waist
    qa = qa_gate(person, rendered)
    assert qa["qa_PASS"] is False
    assert qa["ghost_skin_blobs"] >= 1
    assert any(r.startswith("ghost_limb") for r in qa["qa_reasons"])


def test_face_and_background_drift_low_on_clean():
    person = _scene(torso=DARK)
    rendered = _scene(torso=NAVY)
    assert face_drift(person, rendered) < 0.05
    assert background_drift(person, rendered) < 0.05


def test_face_drift_flags_reimagined_face():
    person = _scene()
    rendered = _scene()
    rendered[0 : int(0.30 * H), :] = (200, 200, 200)  # face band destroyed
    assert face_drift(person, rendered) > 0.25
    assert qa_gate(person, rendered, max_face_drift=0.25)["qa_PASS"] is False


def test_paste_back_identity_restores_face_band():
    person = _scene()
    rendered = _scene(torso=NAVY)
    rendered[0:80, :] = (10, 10, 10)  # diffusion destroyed the face band
    out = np.asarray(paste_back_identity(person, rendered, feather_px=8))
    # inner face band must now equal the person input exactly
    assert np.array_equal(out[0:60, :], person[0:60, :])
    # torso keeps the rendered garment
    assert np.array_equal(out[int(0.5 * H) :, W // 4 : 3 * W // 4], rendered[int(0.5 * H) :, W // 4 : 3 * W // 4])


def test_seed_ladder_is_distinct_and_stable():
    assert len(set(QA_SEED_LADDER)) == len(QA_SEED_LADDER) == 3


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
