"""Stylist image intake: parse, validate and sample uploaded images (Mode A).

Pure functions only (no network, no database). Everything that touches an
uploaded image in the stylist goes through here, so the rules live in one place:

* accepted formats are PNG, JPEG and WebP, and the MAGIC BYTES must agree with
  the declared MIME type (a renamed file is refused, not trusted);
* each decoded image is capped at ``STYLIST_IMAGE_MAX_BYTES``, the number of
  images per turn at ``STYLIST_MAX_IMAGES``. The caps keep one request under the
  serverless request-body ceiling (4.5 MB) once base64 expansion is counted;
* bytes are used for analysis and then dropped. Nothing here writes to storage,
  and the stylist never persists the data URL (see FR-008 / SC-005).
"""
from __future__ import annotations

import base64
import binascii
import colorsys
import io
import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

STYLIST_MAX_IMAGES = 3
#: Decoded size cap per image. 1 MB base64-encodes to ~1.33 MB, so three images
#: plus the prompt stay below the 4.5 MB serverless body ceiling.
STYLIST_IMAGE_MAX_BYTES = 1024 * 1024
STYLIST_IMAGE_MIME_TYPES = ("image/png", "image/jpeg", "image/webp")

_DATA_URL = re.compile(
    r"^data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/]+={0,2})$"
)


class ImageIntakeError(ValueError):
    """An uploaded image was refused. The message is safe to show the shopper."""


@dataclass(frozen=True)
class ParsedImage:
    mime: str
    data: bytes

    @property
    def size_bytes(self) -> int:
        return len(self.data)


def max_encoded_length() -> int:
    """Longest data URL that can carry a decoded image at the byte cap."""
    return ((STYLIST_IMAGE_MAX_BYTES + 2) // 3) * 4 + len("data:image/webp;base64,")


def _magic_matches(mime: str, data: bytes) -> bool:
    if mime == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if mime == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if mime == "image/webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


def parse_image_data_url(value: str) -> ParsedImage:
    """Validate one ``data:image/...;base64,...`` URL and decode it.

    Raises ``ImageIntakeError`` with a shopper-safe reason on any failure.
    """
    if not isinstance(value, str) or not value:
        raise ImageIntakeError("Each image must be a PNG, JPEG or WebP data URL.")
    if len(value) > max_encoded_length():
        raise ImageIntakeError(
            f"Each image must be {STYLIST_IMAGE_MAX_BYTES // (1024 * 1024)} MB or smaller."
        )
    match = _DATA_URL.match(value.strip())
    if not match:
        raise ImageIntakeError("Images must be PNG, JPEG or WebP sent as base64 data URLs.")
    mime, payload = match.group(1), match.group(2)
    try:
        data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise ImageIntakeError("An image could not be decoded.") from None
    if not data:
        raise ImageIntakeError("An image is empty.")
    if len(data) > STYLIST_IMAGE_MAX_BYTES:
        raise ImageIntakeError(
            f"Each image must be {STYLIST_IMAGE_MAX_BYTES // (1024 * 1024)} MB or smaller."
        )
    if not _magic_matches(mime, data):
        raise ImageIntakeError("An image's contents do not match its declared type.")
    return ParsedImage(mime=mime, data=data)


def parse_images(values: Sequence[str]) -> List[ParsedImage]:
    if len(values) > STYLIST_MAX_IMAGES:
        raise ImageIntakeError(f"You can attach up to {STYLIST_MAX_IMAGES} images per message.")
    return [parse_image_data_url(v) for v in values]


# ---------------------------------------------------------------------------
# Deterministic colour extraction (pixels only, no model involved).
# ---------------------------------------------------------------------------

#: Reference points for mapping a sampled RGB colour onto the catalogue's
#: colour-family vocabulary (the same words ColorHarmonyEngine understands).
_FAMILY_REFERENCE: Tuple[Tuple[str, Tuple[int, int, int]], ...] = (
    ("black", (18, 18, 18)),
    ("white", (250, 250, 248)),
    ("ivory", (245, 240, 225)),
    ("cream", (240, 228, 200)),
    ("beige", (216, 199, 181)),
    ("camel", (193, 154, 107)),
    ("tan", (210, 180, 140)),
    ("brown", (110, 70, 45)),
    ("charcoal", (55, 61, 67)),
    ("grey", (128, 128, 128)),
    ("navy", (27, 31, 59)),
    ("denim", (84, 118, 165)),
    ("blue", (40, 90, 200)),
    ("emerald", (30, 120, 90)),
    ("sage", (120, 140, 110)),
    ("olive", (110, 110, 50)),
    ("green", (40, 130, 60)),
    ("gold", (197, 160, 89)),
    ("burgundy", (110, 20, 40)),
    ("red", (200, 30, 40)),
    ("pink", (230, 150, 170)),
    ("purple", (110, 60, 150)),
    ("orange", (230, 120, 40)),
    ("yellow", (240, 210, 60)),
)

_NEUTRAL_FAMILIES = {"black", "white", "ivory", "cream", "beige", "grey", "charcoal", "navy", "camel", "tan", "brown"}


def color_family_for_rgb(rgb: Tuple[int, int, int]) -> str:
    """Nearest catalogue colour family for an sRGB triple.

    Nearest-neighbour in RGB with a saturation/lightness pre-pass: a near-grey
    pixel is reported as a neutral (black/grey/white/beige…) rather than as the
    nearest saturated hue, which is how a grey sweater would otherwise be
    reported as "blue".
    """
    r, g, b = rgb
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    if l < 0.12:
        return "black"
    if l > 0.92 and s < 0.25:
        return "white"
    best = min(
        _FAMILY_REFERENCE,
        key=lambda item: sum((a - c) ** 2 for a, c in zip(item[1], rgb)),
    )[0]
    if s < 0.12:
        return "grey" if l < 0.8 else "white"
    return best


@dataclass(frozen=True)
class PaletteColor:
    hex: str
    family: str
    share: float  # fraction of sampled pixels, 0..1


def extract_palette(image: ParsedImage, *, colors: int = 5, sample_side: int = 96) -> List[PaletteColor]:
    """Dominant colours of an image, most common first.

    Uses Pillow's median-cut quantiser on a downsampled copy. Deterministic for
    identical bytes. Raises ``ImageIntakeError`` if the bytes cannot be opened as
    an image, which is how a corrupt upload is refused.
    """
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - Pillow is a declared dependency
        raise ImageIntakeError("Image analysis is not available in this deployment.") from exc
    try:
        with Image.open(io.BytesIO(image.data)) as opened:
            opened.load()
            rgb = opened.convert("RGB")
    except Exception:  # noqa: BLE001 - any decode failure is a refusal
        raise ImageIntakeError("An image could not be read as a picture.") from None
    rgb.thumbnail((sample_side, sample_side))
    quantised = rgb.quantize(colors=colors, method=Image.Quantize.MEDIANCUT).convert("RGB")
    counts = quantised.getcolors(maxcolors=sample_side * sample_side) or []
    total = sum(count for count, _ in counts) or 1
    palette: List[PaletteColor] = []
    for count, rgb_value in sorted(counts, key=lambda c: c[0], reverse=True):
        hex_value = "#%02X%02X%02X" % rgb_value
        palette.append(PaletteColor(hex=hex_value, family=color_family_for_rgb(rgb_value), share=round(count / total, 4)))
    return palette


def merge_palettes(per_image: Sequence[Sequence[PaletteColor]], limit: int = 6) -> List[PaletteColor]:
    """Combine per-image palettes into one list, merging identical families."""
    shares: dict = {}
    hexes: dict = {}
    for palette in per_image:
        for color in palette:
            shares[color.family] = shares.get(color.family, 0.0) + color.share
            hexes.setdefault(color.family, color.hex)
    total = sum(shares.values()) or 1.0
    ordered = sorted(shares.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return [
        PaletteColor(hex=hexes[family], family=family, share=round(value / total, 4))
        for family, value in ordered
    ]


def is_neutral_family(family: Optional[str]) -> bool:
    return bool(family) and family in _NEUTRAL_FAMILIES
