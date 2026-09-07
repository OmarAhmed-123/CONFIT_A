"""Qwen2.5-VL inference for CONFIT_A's structured fashion-attribute vision.

The model is loaded ONCE (lazy, cached) and served at a single global
concurrency (the Modal class is ``@modal.concurrent(max_inputs=1)``).

Every failure mode is explicit and honest:
* weights missing/corrupt  -> :func:`load_model` raises (worker reports VLM_NOT_READY)
* GPU OOM                  -> :class:`InferenceError`
* non-JSON model output    -> :class:`OutputInvalidError` (caller reports
                              ``analysis_available=False`` — fields are NEVER invented)

torch / transformers / PIL / qwen_vl_utils are imported lazily inside the
functions so :func:`parse_vision_json` (pure) is unit-testable with no ML stack.
"""
from __future__ import annotations

import json
import os
import re
import threading
from typing import Any, Dict

from model_spec import MODEL_REPO_ID, MODEL_REVISION

_MAX_NEW_TOKENS = int(os.environ.get("QWEN_VL_MAX_NEW_TOKENS", "600"))
_MIN_PIXELS = 256 * 28 * 28
_MAX_PIXELS = 1280 * 28 * 28

_state: Dict[str, Any] = {
    "model": None,
    "processor": None,
    "lock": threading.Lock(),
    "loaded": False,
    "load_error": None,
}


class InferenceError(RuntimeError):
    """Infrastructure/model failure (load, decode, OOM)."""


class OutputInvalidError(InferenceError):
    """The model ran but did not return usable STRICT JSON."""


def _weights_dir() -> str:
    return os.environ.get("QWEN_VL_WEIGHTS_DIR", "/weights")


def load_model(device: str = "auto", dtype: str = "bfloat16") -> None:
    """Load the model exactly once. Raises :class:`InferenceError` on any failure."""
    if _state["loaded"]:
        return
    with _state["lock"]:
        if _state["loaded"]:
            return
        try:
            import torch
            from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration
        except ImportError as exc:  # pragma: no cover
            raise InferenceError(f"transformers/torch unavailable in worker: {exc}") from exc

        weights = _weights_dir()
        if not os.path.isfile(os.path.join(weights, "model.safetensors.index.json")):
            raise InferenceError(
                f"weights not present at {weights!r}; mount the Modal volume or run bootstrap_weights.py"
            )

        dtype_map = {"bfloat16": torch.bfloat16, "float16": torch.float16, "float32": torch.float32}
        torch_dtype = dtype_map.get(dtype, torch.bfloat16)
        try:
            model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                weights, torch_dtype=torch_dtype, device_map=device
            )
            model.eval()
            processor = AutoProcessor.from_pretrained(weights)
        except Exception as exc:
            _state["load_error"] = f"{type(exc).__name__}: {exc}"
            raise InferenceError(f"model load failed: {_state['load_error']}") from exc

        _state["model"] = model
        _state["processor"] = processor
        _state["loaded"] = True
        _state["load_error"] = None
        try:
            import torch as _t

            if _t.cuda.is_available():
                print(
                    f"[vlm-load] ok on {_t.cuda.get_device_name(0)}; "
                    f"allocated={_t.cuda.memory_allocated() / 1024**3:.2f}GB "
                    f"reserved={_t.cuda.memory_reserved() / 1024**3:.2f}GB",
                    flush=True,
                )
        except Exception:
            pass


def _get():
    if not _state["loaded"]:
        load_model()
    return _state["model"], _state["processor"]


def parse_vision_json(raw: str) -> Dict[str, Any]:
    """Robustly extract the STRICT JSON object the model was prompted to return.

    PURE (no model/torch) so it is unit-testable without a GPU. Strips markdown
    code fences and surrounding prose, then ``json.loads`` the first balanced
    object. Raises :class:`OutputInvalidError` if no valid JSON object is found.
    """
    if not raw or not raw.strip():
        raise OutputInvalidError("empty model output")
    text = raw.strip()

    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise OutputInvalidError("no JSON object in model output")
        text = text[start : end + 1]

    try:
        data = json.loads(text)
    except Exception as exc:
        raise OutputInvalidError(f"model output is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise OutputInvalidError("model output JSON is not an object")
    return data


def analyze_image(image_bytes: bytes, mime: str, prompt: str) -> Dict[str, Any]:
    """Run one vision inference. Returns the parsed STRICT JSON (no analysis_* keys)."""
    import io

    import torch
    from PIL import Image
    from qwen_vl_utils import process_vision_info

    model, processor = _get()

    pil = Image.open(io.BytesIO(image_bytes))
    pil.load()
    if pil.mode not in ("RGB", "L"):
        pil = pil.convert("RGB")

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": pil},
                {"type": "text", "text": prompt},
            ],
        }
    ]
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image_inputs, video_inputs = process_vision_info(messages)
    inputs = processor(
        text=[text],
        images=image_inputs,
        videos=video_inputs,
        padding=True,
        return_tensors="pt",
    ).to(model.device)
    input_len = inputs["input_ids"].shape[1]

    try:
        with torch.inference_mode():
            generated = model.generate(**inputs, max_new_tokens=_MAX_NEW_TOKENS, do_sample=False)
    except torch.cuda.OutOfMemoryError as exc:
        raise InferenceError(f"GPU OOM during inference: {exc}") from exc

    generated_trimmed = generated[:, input_len:]
    output_text = processor.batch_decode(
        generated_trimmed, skip_special_tokens=True, clean_up_token_spaces=False
    )[0]
    return parse_vision_json(output_text)
