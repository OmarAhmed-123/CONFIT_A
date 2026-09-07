"""Explicit, distinguishable failure modes for the local Qwen2.5-VL vision client.

The design goal is honest failure: the caller (and the fallback routing in
``VisualSearchAIProvider``) must always be able to tell *why* a usable local
analysis was not produced — never a silent "success" without real inference.
"""
from __future__ import annotations


class QwenVisionError(Exception):
    """The self-hosted Qwen2.5-VL vision capability could not produce a usable result.

    ``reason`` is a stable machine-readable code:

    - ``not_configured``     QWEN_VL_WORKER_URL not set, or QWEN_VL_ENABLED is False
    - ``worker_unavailable`` worker host unreachable / connection error
    - ``worker_not_ready``   worker up but model not loaded (503 VLM_NOT_READY)
    - ``worker_error``       worker returned a 5xx inference failure (OOM, etc.)
    - ``invalid_response``   worker returned a non-contract payload
    - ``auth``               worker rejected the admin token (401)
    - ``timeout``            inference exceeded QWEN_VL_TIMEOUT_SECONDS
    - ``bad_input``          the image reference / prompt was rejected pre-flight
    """

    def __init__(
        self,
        reason: str,
        message: str = "",
        *,
        http_status: int | None = None,
    ) -> None:
        super().__init__(f"{reason}: {message}".strip() if message else reason)
        self.reason = reason
        self.message = message
        self.http_status = http_status
