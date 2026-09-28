"""Pilot-tier try-on rendering that satisfies the GPU worker's own contract.

WHY THIS FILE EXISTS
--------------------
`registry.py` and `hf_space_client.py` described and could call the Hugging
Face engines, but nothing in the running service imported them — they were
dead code, and `/try-on/capabilities` still answered
`temporarily_unavailable`. This is the piece that makes the pilot engines
actually serve.

THE CONTRACT IS NOT NEGOTIABLE
------------------------------
`TryOnService._call_gpu_worker` is the single render path, called from three
places. Everything downstream — output validation, the per-layer
`verify.PASS` invariant, job persistence — reads one shape:

    {"rendered_image_data_url": "data:image/...;base64,...",
     "verify": {"PASS": true, ...},
     "model_used": "...", ...}

So this renderer returns exactly that shape rather than a parallel one. A
second shape would mean a second validation path, and the per-layer
verification invariant that protects against "HTTP 200 but the garment was
never applied" would not cover pilot renders.

`verify.PASS` IS MEASURED, NOT ASSERTED
---------------------------------------
The GPU worker computes pixel-change and colour-shift metrics and refuses to
claim success without them. Hugging Face Spaces return an image and nothing
else, so the same evidence is computed HERE, from the person image and the
render. Setting `PASS: True` unconditionally would be a lie of exactly the
kind the surrounding code was written to prevent — and it is a real failure
mode: OOTDiffusion returned HTTP 200 with the garment photo's background
painted onto the person.

MULTI-GARMENT
-------------
No available engine dresses several garments in one pass. Layers are applied
SEQUENTIALLY, each render feeding the next as the person image, and each one
independently verified. Artefacts compound with each pass; that is a property
of the technique, stated rather than hidden.
"""
from __future__ import annotations

import base64
import io
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional, Sequence

import httpx

from backend.app.providers.vton import hf_space_client as hf
from backend.app.providers.vton.prompt import (
    garment_description as build_garment_description,
)
from backend.app.providers.vton.registry import (
    GarmentCategory,
    LicenseTier,
    VtonEngineSpec,
    infer_category,
    resolve_chain,
)

logger = logging.getLogger("confit")

#: Below this fraction of changed pixels the render is treated as "the garment
#: was not applied". Mirrors the GPU worker's own low-pixel-change guard.
MIN_PIXEL_CHANGE = 0.5
#: Mean absolute channel difference. A render that only re-encodes the input
#: shifts colour by ~0.
MIN_COLOR_SHIFT = 0.001


class PilotRenderUnavailable(RuntimeError):
    """No pilot engine may or can serve this request."""


def resolve_tier(raw: Optional[str]) -> LicenseTier:
    """Parse VTON_LICENSE_TIER, defaulting to the SAFER value.

    An unrecognised string resolves to COMMERCIAL, not PILOT: a typo must
    restrict which engines may run, never widen it.
    """
    value = (raw or "").strip().lower()
    return LicenseTier.PILOT if value == "pilot" else LicenseTier.COMMERCIAL


def _fetch_to_temp(ref: str, suffix: str = ".jpg") -> str:
    """Materialise a data URL or http(s) image to a local file."""
    fd, path = tempfile.mkstemp(prefix="vton_in_", suffix=suffix)
    os.close(fd)
    if ref.startswith("data:"):
        _, _, b64_part = ref.partition(",")
        with open(path, "wb") as handle:
            handle.write(base64.b64decode(b64_part))
        return path
    if ref.startswith(("http://", "https://")):
        # SSRF is screened by the caller (is_safe_image_url) before we get here.
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(ref)
            response.raise_for_status()
            with open(path, "wb") as handle:
                handle.write(response.content)
        return path
    raise ValueError("VTON_INPUT_INVALID: image must be a data URL or http(s) URL")


def _measure(before_path: str, after_path: str) -> Dict[str, float]:
    """Evidence that the render actually changed the person.

    Compares the two images at a common small size. Deliberately cheap: this
    runs per layer and only has to distinguish "changed" from "did not".
    """
    from PIL import Image, ImageChops, ImageStat

    with Image.open(before_path) as before_raw, Image.open(after_path) as after_raw:
        before = before_raw.convert("RGB").resize((256, 256))
        after = after_raw.convert("RGB").resize((256, 256))
        diff = ImageChops.difference(before, after)
        stat = ImageStat.Stat(diff)
        # Mean absolute channel difference, normalised to 0..1.
        color_shift = sum(stat.mean) / (3 * 255.0)
        grey = diff.convert("L")
        changed = sum(1 for px in grey.tobytes() if px > 12)
        pixel_change = 100.0 * changed / (256 * 256)
    return {
        "metric_pixel_change": round(pixel_change, 3),
        "metric_color_shift": round(color_shift, 6),
    }


def _to_data_url(path: str) -> str:
    with open(path, "rb") as handle:
        return "data:image/png;base64," + base64.b64encode(handle.read()).decode()


def render_layers(
    *,
    person_image: str,
    garments: Sequence[Dict[str, Any]],
    tier: LicenseTier,
    worker_configured: bool = False,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Dress a person in one or more garments using pilot-tier engines.

    Args:
        person_image: data URL or http(s) URL.
        garments: dicts carrying at least ``image_url``; ``title`` /
            ``category_name`` refine category inference.
        tier: pilot or commercial. COMMERCIAL never reaches a Space engine.
        worker_configured: whether the GPU worker exists (affects the chain).
        job_id: for log correlation only.

    Returns:
        The same dict shape `_call_gpu_worker` produces.

    Raises:
        PilotRenderUnavailable: nothing may or can serve. Never a placeholder
            image — a fabricated render is indistinguishable from a real one.
    """
    if not garments:
        raise ValueError("VTON_GARMENT_ASSET_INVALID: at least one garment required")

    current_person = _fetch_to_temp(person_image)
    base_person = current_person
    applied: List[Dict[str, Any]] = []
    engines_used: List[str] = []
    temp_files = [current_person]

    try:
        for index, garment in enumerate(garments):
            category = infer_category(
                garment.get("category_name"),
                garment.get("title"),
                garment.get("product_title"),
            )
            chain = resolve_chain(
                category, tier, worker_configured=worker_configured
            )
            if not chain:
                # ACCESSORY, or every engine filtered out by licence tier.
                raise PilotRenderUnavailable(
                    f"VTON_CATEGORY_UNSUPPORTED: no engine may render "
                    f"'{category.value}' under the {tier.value} licence tier"
                )

            garment_ref = garment.get("image_url") or ""
            if not garment_ref:
                raise ValueError("VTON_GARMENT_ASSET_INVALID: garment image_url missing")
            garment_path = _fetch_to_temp(garment_ref)
            temp_files.append(garment_path)

            # One builder for every engine: a raw catalogue title carries
            # season codes and marketing words that describe the listing, not
            # the garment.
            description = build_garment_description(
                title=garment.get("title") or garment.get("product_title"),
                category=category,
                colour=garment.get("color") or garment.get("color_family"),
                material=garment.get("material"),
            )
            result = _render_one_with_fallback(
                chain=chain,
                person_path=current_person,
                garment_path=garment_path,
                category=category,
                description=description,
                job_id=job_id,
                layer=index,
            )
            temp_files.append(result["path"])
            # Each layer becomes the person image for the next, which is how
            # a multi-piece outfit is built from single-garment engines.
            current_person = result["path"]
            engines_used.append(result["engine"])
            applied.append(
                {
                    "layer": index,
                    "category": category.value,
                    "engine": result["engine"],
                    "license": result["license"],
                    "commercial": result["commercial"],
                    "elapsed_seconds": result["elapsed_seconds"],
                    **result["metrics"],
                }
            )

        # Verification is against the ORIGINAL person, not the previous layer:
        # the question downstream asks is whether the person was dressed.
        metrics = _measure(base_person, current_person)
        passed = (
            metrics["metric_pixel_change"] >= MIN_PIXEL_CHANGE
            and metrics["metric_color_shift"] >= MIN_COLOR_SHIFT
        )
        if not passed:
            logger.error(
                "vton_pilot_layer_not_applied",
                extra={"job_id": job_id, **metrics},
            )

        return {
            "rendered_image_data_url": _to_data_url(current_person),
            "model_used": "+".join(engines_used),
            "verify": {
                # Measured from the pixels, never assumed. An engine can
                # return HTTP 200 and an unchanged person.
                "PASS": bool(passed),
                **metrics,
            },
            "engine_tier": tier.value,
            "layers": applied,
            # Carried so a pilot render made by a non-commercial model stays
            # identifiable once the platform starts trading.
            "commercial_safe": all(layer["commercial"] for layer in applied),
        }
    finally:
        for path in temp_files:
            try:
                os.unlink(path)
            except OSError:
                pass


def _render_one_with_fallback(
    *,
    chain: Sequence[VtonEngineSpec],
    person_path: str,
    garment_path: str,
    category: GarmentCategory,
    description: str,
    job_id: Optional[str],
    layer: int,
) -> Dict[str, Any]:
    """Try each engine in order; keep the first render that measurably changed.

    A render that produced an image but did not change the person is treated
    as a FAILURE and the chain advances, because that is indistinguishable
    from success to everything downstream.
    """
    errors: List[str] = []
    for spec in chain:
        try:
            result = hf.render(
                spec,
                person_image_path=person_path,
                garment_image_path=garment_path,
                category=category,
                garment_description=description,
            )
        except Exception as exc:  # engine-level failure: advance the chain
            errors.append(f"{spec.key}: {str(exc)[:120]}")
            logger.warning(
                "vton_pilot_engine_failed",
                extra={"job_id": job_id, "engine": spec.key, "layer": layer},
            )
            continue

        metrics = _measure(person_path, result.image_path)
        if metrics["metric_pixel_change"] < MIN_PIXEL_CHANGE:
            errors.append(
                f"{spec.key}: rendered but did not change the person "
                f"({metrics['metric_pixel_change']}% pixels)"
            )
            try:
                os.unlink(result.image_path)
            except OSError:
                pass
            continue

        return {
            "path": result.image_path,
            "engine": result.engine,
            "license": result.license,
            "commercial": result.commercial,
            "elapsed_seconds": result.elapsed_seconds,
            "metrics": metrics,
        }

    raise PilotRenderUnavailable(
        "VTON_ENGINE_UNAVAILABLE: every pilot engine failed for "
        f"{category.value} — " + "; ".join(errors)
    )
