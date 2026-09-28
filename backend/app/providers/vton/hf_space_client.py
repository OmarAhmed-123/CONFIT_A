"""Adapter for try-on engines hosted as Hugging Face Spaces.

TRANSPORT CHOICE
----------------
Spaces expose a Gradio API. `yisol/IDM-VTON` runs Gradio 4.x, whose REST
surface is NOT the `/gradio_api/*` shape of Gradio 5 — a hand-rolled HTTP
client against it returns 404 (measured 2026-09-27). `gradio_client` resolves
the protocol version per Space, so it is used instead of re-implementing two
wire formats that will drift.

It is imported LAZILY. The package pulls in a substantial dependency tree and
this is a pilot-tier code path; a deployment that never renders must not pay
for it at import time, and the API must still boot if it is absent.

WHAT THIS DOES NOT DO
---------------------
No retry-across-engines: that is the caller's job via `registry.resolve_chain`,
so the fallback order stays a single, testable decision rather than being
re-litigated inside each adapter.
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from typing import Optional

from backend.app.providers.vton.registry import GarmentCategory, VtonEngineSpec

logger = logging.getLogger("confit")

#: Spaces are shared ZeroGPU hardware and queue. Measured cold runs:
#: IDM-VTON 24.0s, OOTDiffusion 15.4s. The ceiling allows for a queue without
#: holding a request open indefinitely.
DEFAULT_TIMEOUT_SECONDS = 180.0


class VtonRenderError(RuntimeError):
    """Raised when an engine could not produce an image.

    Carries `engine` and `retryable` so the caller can decide between
    advancing the chain and giving up, without parsing a message string.
    """

    def __init__(self, message: str, *, engine: str, retryable: bool = True):
        super().__init__(message)
        self.engine = engine
        self.retryable = retryable


@dataclass(frozen=True)
class VtonRenderResult:
    """A produced image plus how it was produced.

    `engine` and `license` travel WITH the render because a pilot-tier image
    made by a non-commercial model must remain identifiable after the fact —
    when the platform starts trading, those assets have to be findable.
    """

    image_path: str
    engine: str
    license: str
    commercial: bool
    elapsed_seconds: float
    category: str


#: Gradio `category` values differ per Space; the registry stays canonical.
_OOTD_CATEGORY = {
    GarmentCategory.UPPER: "Upper-body",
    GarmentCategory.LOWER: "Lower-body",
    GarmentCategory.DRESS: "Dress",
}


def _import_gradio(engine: str):
    """Single ImportError boundary for the optional gradio_client dependency.

    Both symbols are resolved here so there is exactly ONE guarded import
    site. A second, unguarded `from gradio_client import ...` further down
    would crash the request instead of degrading — which is precisely the
    failure mode the deployment dependency gate exists to catch, and why
    `gradio_client` may be listed as optional for the Vercel target.
    """
    try:
        from gradio_client import Client, handle_file  # noqa: WPS433
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise VtonRenderError(
            "gradio_client is not installed; Hugging Face Space engines are "
            "unavailable in this deployment",
            engine=engine,
            retryable=False,
        ) from exc
    return Client, handle_file


def _load_client(space: str, timeout: float):
    Client, _ = _import_gradio(space)
    try:
        return Client(space, verbose=False, httpx_kwargs={"timeout": timeout})
    except TypeError:
        # Older gradio_client has no httpx_kwargs.
        return Client(space, verbose=False)
    except Exception as exc:
        raise VtonRenderError(
            f"Space {space} is not reachable: {exc}", engine=space
        ) from exc


def render(
    spec: VtonEngineSpec,
    *,
    person_image_path: str,
    garment_image_path: str,
    category: GarmentCategory,
    garment_description: str = "",
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> VtonRenderResult:
    """Render one garment onto one person with a single engine.

    Raises:
        VtonRenderError: the engine was unreachable, refused, or returned
            something that was not an image. Never returns a placeholder —
            a fabricated "result" would be indistinguishable from a real one.
    """
    if spec.transport != "hf_space":
        raise VtonRenderError(
            f"{spec.key} is a {spec.transport} engine, not a Space",
            engine=spec.key,
            retryable=False,
        )

    _, handle_file = _import_gradio(spec.key)
    client = _load_client(spec.endpoint, timeout)
    started = time.time()

    try:
        if spec.key == "idm_vton_hf":
            raw = client.predict(
                dict={
                    "background": handle_file(person_image_path),
                    "layers": [],
                    "composite": None,
                },
                garm_img=handle_file(garment_image_path),
                garment_des=garment_description or "",
                # Auto-masking is what lets this engine accept an on-model
                # catalogue photo instead of a flat-lay cut-out.
                is_checked=True,
                is_checked_crop=False,
                denoise_steps=int(spec.extra.get("denoise_steps", 30)),
                seed=42,
                api_name=spec.api_name,
            )
        elif spec.key == "ootd_hf":
            mapped = _OOTD_CATEGORY.get(category)
            if mapped is None:
                raise VtonRenderError(
                    f"{spec.key} cannot render {category.value}",
                    engine=spec.key,
                    retryable=False,
                )
            raw = client.predict(
                vton_img=handle_file(person_image_path),
                garm_img=handle_file(garment_image_path),
                category=mapped,
                n_samples=1,
                n_steps=int(spec.extra.get("n_steps", 20)),
                image_scale=float(spec.extra.get("image_scale", 2.0)),
                seed=42,
                api_name=spec.api_name,
            )
        elif spec.key == "leffa_hf":
            raw = client.predict(
                src_image_path=handle_file(person_image_path),
                ref_image_path=handle_file(garment_image_path),
                api_name=spec.api_name,
            )
        else:
            raise VtonRenderError(
                f"No Space adapter for engine {spec.key}",
                engine=spec.key,
                retryable=False,
            )
    except VtonRenderError:
        raise
    except Exception as exc:
        raise VtonRenderError(
            f"{spec.key} render failed: {exc}", engine=spec.key
        ) from exc

    path = _first_image_path(raw)
    if not path or not os.path.exists(path):
        raise VtonRenderError(
            f"{spec.key} returned no image (got {type(raw).__name__})",
            engine=spec.key,
        )

    # Copy out of the client's temp dir: it is cleaned up unpredictably.
    fd, dest = tempfile.mkstemp(prefix=f"vton_{spec.key}_", suffix=".png")
    os.close(fd)
    shutil.copy(path, dest)

    elapsed = time.time() - started
    logger.info(
        "vton_render_ok",
        extra={"engine": spec.key, "category": category.value,
               "elapsed_seconds": round(elapsed, 2), "commercial": spec.commercial},
    )
    return VtonRenderResult(
        image_path=dest,
        engine=spec.key,
        license=spec.license,
        commercial=spec.commercial,
        elapsed_seconds=elapsed,
        category=category.value,
    )


def _first_image_path(raw: object) -> Optional[str]:
    """Pull a filepath out of the several shapes Gradio returns.

    IDM-VTON returns a 2-tuple of paths, OOTDiffusion a list of gallery dicts,
    Leffa a bare path. Normalised here so the caller sees one contract.
    """
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        for key in ("image", "path", "name", "url"):
            value = raw.get(key)
            if isinstance(value, str):
                return value
        return None
    if isinstance(raw, (list, tuple)):
        for item in raw:
            found = _first_image_path(item)
            if found:
                return found
    return None
