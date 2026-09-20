from __future__ import annotations

import sys
from pathlib import Path

import pytest

EVAL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EVAL_ROOT))


@pytest.fixture
def solid_img(tmp_path):
    from PIL import Image
    img = Image.new("RGB", (200, 200), (35, 53, 92))
    p = tmp_path / "solid.jpg"
    img.save(p, "JPEG", quality=95)
    return p


@pytest.fixture
def stripe_img(tmp_path):
    """Deterministic vertical-stripe image: 20px black + 20px white runs => 40px period (scaled to ~26px at 128px)."""
    from PIL import Image
    import numpy as np
    arr = np.zeros((200, 200, 3), dtype=np.uint8)
    for x in range(200):
        arr[:, x] = 0 if (x // 20) % 2 == 0 else 255
    p = tmp_path / "stripes.jpg"
    Image.fromarray(arr).save(p, "JPEG", quality=95)
    return p


@pytest.fixture
def text_img(tmp_path):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (600, 200), (255, 255, 255))
    ImageDraw.Draw(img).text((100, 80), "STUDIO 2026", fill=(0, 0, 0))
    p = tmp_path / "text.jpg"
    img.save(p, "JPEG", quality=95)
    return p


@pytest.fixture
def blank_img(tmp_path):
    """Uniform gray — no face, no pose, no garment (malformed-input fixture)."""
    from PIL import Image
    img = Image.new("RGB", (300, 400), (128, 128, 128))
    p = tmp_path / "blank.jpg"
    img.save(p, "JPEG", quality=95)
    return p
