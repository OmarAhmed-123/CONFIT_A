"""Typed failures for the NVIDIA NIM provider.

Split by REMEDIATION, not by HTTP code — the client needs to answer one
question per failure: *rotate the key, try the next model, or give up?*
"""
from __future__ import annotations

from typing import Optional


class NvidiaProviderError(RuntimeError):
    """Base class. Never carries a credential — only the redacted form."""

    def __init__(self, message: str, *, model_id: Optional[str] = None,
                 status: Optional[int] = None, key_hint: Optional[str] = None) -> None:
        self.model_id = model_id
        self.status = status
        self.key_hint = key_hint
        detail = message
        if model_id:
            detail += f" [model={model_id}]"
        if status is not None:
            detail += f" [http={status}]"
        if key_hint:
            detail += f" [key={key_hint}]"
        super().__init__(detail)


class NvidiaNotConfigured(NvidiaProviderError):
    """No usable credential was found. Callers should fail over to another
    provider, or degrade honestly — never fabricate a result."""


class NvidiaCapacityError(NvidiaProviderError):
    """429 / 503 ResourceExhausted. ROTATE THE KEY and retry the same model."""


class NvidiaAuthError(NvidiaProviderError):
    """401 / 403. The credential is dead. Drop it and try another key; if the
    whole pool fails this way it is an operational incident, not a blip."""


class NvidiaModelGoneError(NvidiaProviderError):
    """404 / 410. The model id itself is wrong or end-of-lifed — exactly what
    silently broke `meta/llama-3.1-70b-instruct` on 2026-08-26. Rotating keys
    cannot help; advance to the next model in the role chain and log loudly."""


class NvidiaEmptyResponseError(NvidiaProviderError):
    """HTTP 200 with no usable content — typically a reasoning model that spent
    its whole token budget in `reasoning_content`. Treated as a failure so the
    chain advances instead of surfacing an empty answer to a shopper."""


class NvidiaTimeoutError(NvidiaProviderError):
    """The per-attempt deadline expired. Advance the chain; do not extend the
    deadline, because a user request is waiting behind it."""
