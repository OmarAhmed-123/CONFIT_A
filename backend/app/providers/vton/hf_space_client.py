"""Hugging Face Space try-on engines over plain HTTP.

WHY NOT `gradio_client`
-----------------------
It worked, and it cost too much. The Vercel build reported:

    Bundle size (263.17 MB) exceeds the standard size; optimizing dependencies

against a 250 MB Python function limit — `gradio_client` drags in
`huggingface_hub`, `fsspec`, `pandas` and friends. Vercel then prunes to fit,
which is a silent, non-deterministic edit of the runtime; the try-on engines
were the thing most likely to lose. It also writes a cache tree under $HOME,
which is read-only on a serverless filesystem.

The Space speaks an ordinary HTTP protocol. Implementing it with `httpx` —
already a dependency of this project — removes the whole tree and the cache
problem with it.

THE PROTOCOL (Gradio 4.x, verified against yisol/IDM-VTON @ 4.24.0)
--------------------------------------------------------------------
    GET  /config                  -> api_name -> fn_index, and the version
    POST /upload    (multipart)   -> ["/tmp/gradio/<hash>/<name>", ...]
    POST /queue/join (json)       -> {"event_id": ...}
    GET  /queue/data?session_hash -> SSE; "process_completed" carries the output

Note the paths: Gradio 5 moved these under `/gradio_api/*`, and the Spaces
used here are 4.x, where that prefix 404s. `fn_index` is resolved from
`/config` by `api_name` rather than hard-coded, so a Space that re-orders its
functions does not silently invoke the wrong one.

WHAT THIS DOES NOT DO
---------------------
No retry across engines: that is `registry.resolve_chain` plus
`pilot_renderer`, so the fallback order stays one testable decision instead
of being re-litigated in every adapter.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from backend.app.providers.vton.registry import GarmentCategory, VtonEngineSpec

logger = logging.getLogger("confit")

#: Spaces run on shared ZeroGPU hardware and queue. Measured cold runs:
#: IDM-VTON 22.2s direct, OOTDiffusion 15.4s. The ceiling allows for a queue
#: without holding a request open indefinitely.
DEFAULT_TIMEOUT_SECONDS = 180.0

#: `/config` rarely changes; resolving it per render would add a round trip to
#: every layer of a multi-garment outfit.
_CONFIG_CACHE: Dict[str, Dict[str, Any]] = {}


class VtonRenderError(RuntimeError):
    """An engine could not produce an image.

    Carries `engine` and `retryable` so the caller can choose between
    advancing the chain and giving up, without parsing a message string.
    """

    def __init__(self, message: str, *, engine: str, retryable: bool = True):
        super().__init__(message)
        self.engine = engine
        self.retryable = retryable


@dataclass(frozen=True)
class VtonRenderResult:
    """A produced image plus how it was produced.

    `engine` and `license` travel WITH the render: a pilot-tier image made by
    a non-commercial model must stay identifiable once the platform trades.
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


def _space_base(endpoint: str) -> str:
    """`owner/name` -> `https://owner-name.hf.space`."""
    if endpoint.startswith("http"):
        return endpoint.rstrip("/")
    slug = endpoint.replace("/", "-").replace("_", "-").replace(".", "-").lower()
    return f"https://{slug}.hf.space"


def _fn_index(client: httpx.Client, base: str, api_name: str, engine: str) -> int:
    """Resolve an api_name to its fn_index via /config.

    Resolved rather than hard-coded: a Space that adds or reorders functions
    would otherwise make us invoke a different one and return a plausible
    wrong image.
    """
    config = _CONFIG_CACHE.get(base)
    if config is None:
        try:
            response = client.get(f"{base}/config")
            response.raise_for_status()
            config = response.json()
        except Exception as exc:
            raise VtonRenderError(
                f"{engine}: cannot read Space config: {exc}", engine=engine
            ) from exc
        _CONFIG_CACHE[base] = config

    wanted = api_name.lstrip("/")
    for index, dep in enumerate(config.get("dependencies") or []):
        if (dep.get("api_name") or "").lstrip("/") == wanted:
            return index
    raise VtonRenderError(
        f"{engine}: Space exposes no api_name '{wanted}'",
        engine=engine,
        retryable=False,
    )


def _upload(client: httpx.Client, base: str, paths: List[str], engine: str) -> List[str]:
    files = [
        ("files", (os.path.basename(p), open(p, "rb"), "image/jpeg")) for p in paths
    ]
    try:
        response = client.post(f"{base}/upload", files=files)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        raise VtonRenderError(
            f"{engine}: upload failed: {exc}", engine=engine
        ) from exc
    finally:
        for _, (_, handle, _) in files:
            try:
                handle.close()
            except Exception:
                pass


def _file_ref(base: str, server_path: str) -> Dict[str, Any]:
    """The FileData shape Gradio expects for an uploaded file."""
    return {
        "path": server_path,
        "url": f"{base}/file={server_path}",
        "orig_name": os.path.basename(server_path),
        "size": None,
        "mime_type": "image/jpeg",
        "meta": {"_type": "gradio.FileData"},
    }


def _run(
    client: httpx.Client,
    base: str,
    fn_index: int,
    data: List[Any],
    engine: str,
) -> List[Any]:
    """Queue a call and read the SSE stream until it completes."""
    session_hash = uuid.uuid4().hex[:11]
    try:
        join = client.post(
            f"{base}/queue/join",
            json={
                "data": data,
                "event_data": None,
                "fn_index": fn_index,
                "trigger_id": None,
                "session_hash": session_hash,
            },
        )
        join.raise_for_status()
    except Exception as exc:
        raise VtonRenderError(
            f"{engine}: queue/join failed: {exc}", engine=engine
        ) from exc

    try:
        with client.stream(
            "GET", f"{base}/queue/data", params={"session_hash": session_hash}
        ) as stream:
            for line in stream.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                message = json.loads(line[5:])
                kind = message.get("msg")
                if kind == "process_completed":
                    output = message.get("output") or {}
                    if output.get("error"):
                        raise VtonRenderError(
                            f"{engine}: Space reported: {str(output['error'])[:200]}",
                            engine=engine,
                        )
                    return output.get("data") or []
                if kind == "unexpected_error":
                    raise VtonRenderError(
                        f"{engine}: {str(message.get('message'))[:200]}", engine=engine
                    )
    except VtonRenderError:
        raise
    except Exception as exc:
        raise VtonRenderError(
            f"{engine}: result stream failed: {exc}", engine=engine
        ) from exc

    raise VtonRenderError(f"{engine}: stream ended with no result", engine=engine)


def _download(
    client: httpx.Client, base: str, raw: Any, engine: str
) -> str:
    """Fetch the first image the Space returned to a local temp file."""
    ref = _first_file_ref(raw)
    if not ref:
        raise VtonRenderError(
            f"{engine}: no image in the Space output", engine=engine
        )
    url = ref if str(ref).startswith("http") else f"{base}/file={ref}"
    try:
        response = client.get(url)
        response.raise_for_status()
        payload = response.content
    except Exception as exc:
        raise VtonRenderError(
            f"{engine}: could not fetch the rendered image: {exc}", engine=engine
        ) from exc
    if len(payload) < 1000:
        raise VtonRenderError(
            f"{engine}: rendered image is implausibly small ({len(payload)} bytes)",
            engine=engine,
        )
    fd, dest = tempfile.mkstemp(prefix=f"vton_{engine}_", suffix=".png")
    os.close(fd)
    with open(dest, "wb") as handle:
        handle.write(payload)
    return dest


def _first_file_ref(raw: Any) -> Optional[str]:
    """Pull a url/path out of the shapes these Spaces return.

    IDM-VTON returns two FileData dicts, OOTDiffusion a gallery list, Leffa a
    bare path. Normalised here so the caller sees one contract.
    """
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        for key in ("url", "path", "name", "image", "video"):
            value = raw.get(key)
            found = _first_file_ref(value) if not isinstance(value, str) else value
            if found:
                return found
        return None
    if isinstance(raw, (list, tuple)):
        for item in raw:
            found = _first_file_ref(item)
            if found:
                return found
    return None


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
        VtonRenderError: unreachable, refused, or returned something that was
            not an image. Never a placeholder — a fabricated "result" is
            indistinguishable from a real one to everything downstream.
    """
    if spec.transport != "hf_space":
        raise VtonRenderError(
            f"{spec.key} is a {spec.transport} engine, not a Space",
            engine=spec.key,
            retryable=False,
        )

    base = _space_base(spec.endpoint)
    started = time.time()

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        fn_index = _fn_index(client, base, spec.api_name, spec.key)
        uploaded = _upload(
            client, base, [person_image_path, garment_image_path], spec.key
        )
        person_ref = _file_ref(base, uploaded[0])
        garment_ref = _file_ref(base, uploaded[1])

        if spec.key == "idm_vton_hf":
            data = [
                # ImageEditor component: the photo is the "background" layer.
                {"background": person_ref, "layers": [], "composite": None},
                garment_ref,
                garment_description or "",
                # Auto-masking: what lets this engine accept an on-model
                # catalogue photo instead of a flat-lay cut-out.
                True,
                False,
                int(spec.extra.get("denoise_steps", 30)),
                42,
            ]
        elif spec.key == "ootd_hf":
            mapped = _OOTD_CATEGORY.get(category)
            if mapped is None:
                raise VtonRenderError(
                    f"{spec.key} cannot render {category.value}",
                    engine=spec.key,
                    retryable=False,
                )
            data = [
                person_ref,
                garment_ref,
                mapped,
                1,
                int(spec.extra.get("n_steps", 20)),
                float(spec.extra.get("image_scale", 2.0)),
                42,
            ]
        elif spec.key == "leffa_hf":
            data = [person_ref, garment_ref]
        else:
            raise VtonRenderError(
                f"No Space adapter for engine {spec.key}",
                engine=spec.key,
                retryable=False,
            )

        output = _run(client, base, fn_index, data, spec.key)
        image_path = _download(client, base, output, spec.key)

    elapsed = time.time() - started
    logger.info(
        "vton_render_ok",
        extra={
            "engine": spec.key,
            "category": category.value,
            "elapsed_seconds": round(elapsed, 2),
            "commercial": spec.commercial,
        },
    )
    return VtonRenderResult(
        image_path=image_path,
        engine=spec.key,
        license=spec.license,
        commercial=spec.commercial,
        elapsed_seconds=elapsed,
        category=category.value,
    )
