"""NVIDIA NIM provider for CONFIT_A.

Role-routed access to the NVIDIA API catalogue. Services import a ROLE, never
a model id, so swapping models is a one-line registry change.

    from backend.app.providers.nvidia import ModelRole, nvidia_client

    result = await nvidia_client.chat(
        ModelRole.STYLIST_CHAT, system=..., user=...)

See ``docs/NVIDIA_MODEL_ROUTING.md`` for the measured evidence behind every
binding, and ``backend/scripts/verify_nvidia_models.py`` to re-verify it.
"""
from backend.app.providers.nvidia.client import (
    ChatResult,
    EmbeddingResult,
    ImagePart,
    NvidiaClient,
    nvidia_client,
)
from backend.app.providers.nvidia.errors import (
    NvidiaAuthError,
    NvidiaCapacityError,
    NvidiaEmptyResponseError,
    NvidiaModelGoneError,
    NvidiaNotConfigured,
    NvidiaProviderError,
    NvidiaTimeoutError,
)
from backend.app.providers.nvidia.keypool import NvidiaKeyPool, key_pool, redact
from backend.app.providers.nvidia.registry import (
    ROLE_CHAINS,
    UNROUTED_MODELS,
    ModelRole,
    ModelSpec,
    all_routed_model_ids,
    describe,
    find_spec,
    get_chain,
    get_primary,
)

__all__ = [
    "ChatResult",
    "EmbeddingResult",
    "ImagePart",
    "ModelRole",
    "ModelSpec",
    "NvidiaAuthError",
    "NvidiaCapacityError",
    "NvidiaClient",
    "NvidiaEmptyResponseError",
    "NvidiaKeyPool",
    "NvidiaModelGoneError",
    "NvidiaNotConfigured",
    "NvidiaProviderError",
    "NvidiaTimeoutError",
    "ROLE_CHAINS",
    "UNROUTED_MODELS",
    "all_routed_model_ids",
    "describe",
    "find_spec",
    "get_chain",
    "get_primary",
    "key_pool",
    "nvidia_client",
    "redact",
]
