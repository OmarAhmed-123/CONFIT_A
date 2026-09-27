"""Async NVIDIA NIM client — role-routed, key-rotating, fail-honest.

Call it by ROLE, never by model id::

    from backend.app.providers.nvidia import NvidiaClient, ModelRole

    client = NvidiaClient()
    result = await client.chat(
        ModelRole.STYLIST_CHAT,
        system="You are CONFIT's Senior AI Fashion Director...",
        user="smart casual dinner in Cairo, budget 400",
    )
    result.text       # grounded prose
    result.model_id   # the model that ACTUALLY served it
    result.latency_s  # measured, for the truthfulness tests

Design rules, each one traceable to something measured on 2026-09-27:

* **The served model is reported, never the requested one.** The response's
  echoed ``model`` field wins. ``test_ai_model_truthfulness.py`` already
  exists because a previous provider claimed one model and called another.
* **HTTP 200 is not success.** ``moonshotai/kimi-k3`` returned 200 with empty
  ``content`` and garbage ``reasoning_content`` ("The!!!!!!!!..."), and
  ``google/diffusiongemma`` returned 200 with no content at all. Both are
  raised as :class:`NvidiaEmptyResponseError` so the chain advances.
* **Capacity failures rotate the credential, not the model.** 503
  ``ResourceExhausted`` is a per-worker ceiling, and every key reaches a
  different worker pool.
* **410 Gone advances the model and logs at ERROR.** This is the exact failure
  that sat undetected in ``orchestrator.py`` for a month.
* **Reasoning traces never reach a caller.** ``reasoning_content`` is dropped;
  ``<think>`` blocks are stripped; markdown JSON fences are removed.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

import httpx

from backend.app.core.logging import logger
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
    EMBEDDINGS_URL,
    ModelRole,
    ModelSpec,
    get_chain,
)

#: Per-attempt wall clock. Deliberately per-ATTEMPT, not per-call: the role
#: chain may make several attempts and each one gets its own honest deadline.
DEFAULT_TIMEOUT_S = 20.0
#: Key rotations per model before giving up on that model. 3 covers the
#: observed transient 503s without turning one request into a retry storm.
DEFAULT_KEY_ATTEMPTS = 3

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_JSON_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)

#: Content type for a multimodal message part.
ImageInput = Union[str, "ImagePart"]


@dataclass(frozen=True)
class ImagePart:
    """An image for a vision call.

    ``url`` may be an https URL or a ``data:image/jpeg;base64,...`` URI — both
    were verified working against the NIM vision models.
    """

    url: str


@dataclass(frozen=True)
class ChatResult:
    """A completed, validated chat call."""

    text: str
    model_id: str            #: what the endpoint said it served
    requested_model_id: str  #: what we asked for
    role: str
    latency_s: float
    attempts: int
    finish_reason: Optional[str] = None
    usage: Mapping[str, Any] = None  # type: ignore[assignment]

    @property
    def engine_label(self) -> str:
        """Attribution string for the stylist contract, e.g.
        ``"NVIDIA nvidia/nemotron-3-ultra-550b-a55b"``. Built from the SERVED
        model so it can never overstate what answered."""
        return f"NVIDIA {self.model_id}"


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: List[List[float]]
    model_id: str
    latency_s: float

    @property
    def dimension(self) -> int:
        return len(self.vectors[0]) if self.vectors else 0


class NvidiaClient:
    """Role-routed NVIDIA NIM client.

    Stateless apart from the shared credential pool, so a single instance is
    safe to reuse across the app and across concurrent requests.
    """

    def __init__(
        self,
        pool: Optional[NvidiaKeyPool] = None,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        key_attempts: int = DEFAULT_KEY_ATTEMPTS,
    ) -> None:
        self._pool = pool or key_pool
        self._timeout_s = timeout_s
        self._key_attempts = max(1, key_attempts)

    # ── public API ───────────────────────────────────────────────────────────

    @property
    def configured(self) -> bool:
        return self._pool.configured

    def status(self) -> Dict[str, Any]:
        """Credential-free health snapshot."""
        return {"provider": "nvidia", "keys": self._pool.status()}

    async def chat(
        self,
        role: ModelRole,
        *,
        user: str,
        system: Optional[str] = None,
        images: Optional[Sequence[ImageInput]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        timeout_s: Optional[float] = None,
        model_id: Optional[str] = None,
        pin_strict: bool = False,
        extra_params: Optional[Mapping[str, Any]] = None,
    ) -> ChatResult:
        """Run a chat completion for ``role``, walking its failover chain.

        Parameters
        ----------
        model_id:
            Pin one specific model from the role's chain — this is the hook for
            "use model X for this part". If the id is not in the chain a
            ``ValueError`` is raised rather than silently falling back, so a
            typo cannot quietly route traffic somewhere unintended.
        pin_strict:
            With ``model_id``, forbid failover entirely: if that one model
            cannot answer, raise. Use it when the choice of model is part of
            the requirement (a benchmark, an A/B arm, a compliance-pinned
            path) and a silent substitution would invalidate the result.
            Key rotation still applies — that changes the credential, not the
            model. Leave it False on user-facing paths, where answering with
            the failover model beats not answering.

        Raises
        ------
        NvidiaNotConfigured, NvidiaProviderError
            Every candidate failed. The caller must degrade honestly (the
            deterministic StylingEngine, or ``analysis_available=False``) —
            it must never invent content.
        """
        chain = self._resolve_chain(role, model_id, pin_strict)
        if not self._pool.configured:
            raise NvidiaNotConfigured(
                "No NVIDIA credential is present in the environment",
            )

        messages = self._build_messages(system, user, images)
        deadline = timeout_s or self._timeout_s
        last_error: Optional[Exception] = None
        attempts = 0

        for spec in chain:
            if images and not spec.supports_vision:
                logger.info(
                    "nvidia_skip_non_vision_model",
                    role=role.value, model=spec.model_id,
                    reason="request carries images; this model is text-only",
                )
                continue

            payload = self._build_chat_payload(
                spec, messages, max_tokens=max_tokens, temperature=temperature,
                extra_params=extra_params,
            )

            for key in self._pool.candidates(spec.slot_key_env, limit=self._key_attempts):
                attempts += 1
                started = time.perf_counter()
                try:
                    data = await self._post(spec.endpoint, key, payload, deadline)
                except NvidiaCapacityError as exc:
                    last_error = exc
                    logger.warn(
                        "nvidia_capacity_rotating_key",
                        role=role.value, model=spec.model_id,
                        key=redact(key), status=exc.status,
                        note="per-worker request ceiling hit; retrying on the next pooled credential",
                    )
                    continue
                except NvidiaAuthError as exc:
                    last_error = exc
                    logger.error(
                        "ALERT nvidia_credential_rejected",
                        role=role.value, model=spec.model_id,
                        key=redact(key), status=exc.status,
                        action_required="rotate or re-issue this NVIDIA API key",
                    )
                    continue
                except NvidiaModelGoneError as exc:
                    last_error = exc
                    logger.error(
                        "ALERT nvidia_model_end_of_life",
                        role=role.value, model=spec.model_id, status=exc.status,
                        action_required=(
                            "update backend/app/providers/nvidia/registry.py — "
                            "this model no longer exists at the endpoint"
                        ),
                    )
                    break  # another key cannot resurrect a dead model
                except (NvidiaTimeoutError, NvidiaProviderError) as exc:
                    last_error = exc
                    logger.warn("nvidia_attempt_failed", role=role.value,
                                model=spec.model_id, error=str(exc))
                    break

                elapsed = time.perf_counter() - started
                try:
                    return self._accept_chat(role, spec, data, elapsed, attempts)
                except NvidiaEmptyResponseError as exc:
                    last_error = exc
                    logger.error(
                        "ai_provider_empty_response",
                        provider="nvidia", requested_model=spec.model_id,
                        model_served=str(data.get("model")), cause=str(exc),
                        action_required="advance to the next model in the role chain",
                    )
                    break  # a different key will produce the same empty answer

        raise self._exhausted(role, chain, attempts, last_error)

    async def embed(
        self,
        texts: Sequence[str],
        *,
        input_type: str = "query",
        timeout_s: Optional[float] = None,
    ) -> EmbeddingResult:
        """Dense vectors for ``texts``.

        Wired but intentionally unused: MODEL_REGISTRY.json records that CONFIT
        has no vector-retrieval feature, and it forbids shipping an unused
        embedding model. Do not call this from a product path until a pgvector
        chain is explicitly approved.
        """
        spec = get_chain(ModelRole.EMBEDDING)[0]
        if not self._pool.configured:
            raise NvidiaNotConfigured("No NVIDIA credential is present in the environment")

        payload: Dict[str, Any] = {
            "model": spec.model_id,
            "input": list(texts),
            **dict(spec.params),
            "input_type": input_type,
        }
        deadline = timeout_s or self._timeout_s
        last_error: Optional[Exception] = None

        for key in self._pool.candidates(spec.slot_key_env, limit=self._key_attempts):
            started = time.perf_counter()
            try:
                data = await self._post(EMBEDDINGS_URL, key, payload, deadline)
            except NvidiaCapacityError as exc:
                last_error = exc
                continue
            except NvidiaProviderError as exc:
                last_error = exc
                break
            rows = data.get("data") or []
            vectors = [r.get("embedding") or [] for r in rows if isinstance(r, dict)]
            if not vectors or not vectors[0]:
                raise NvidiaEmptyResponseError(
                    "embeddings response contained no vectors", model_id=spec.model_id)
            return EmbeddingResult(
                vectors=vectors,
                model_id=data.get("model") or spec.model_id,
                latency_s=round(time.perf_counter() - started, 3),
            )

        raise NvidiaProviderError(
            f"NVIDIA embeddings failed: {last_error}", model_id=spec.model_id)

    async def chat_json(
        self,
        role: ModelRole,
        *,
        user: str,
        system: Optional[str] = None,
        images: Optional[Sequence[ImageInput]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """``chat`` plus strict JSON parsing.

        Needed because ``google/gemma-4-31b-it`` wraps its JSON in a ```json
        fence while ``google/diffusiongemma`` returns it bare — a caller must
        not have to know which model answered.
        """
        result = await self.chat(role, user=user, system=system, images=images, **kwargs)
        raw = _strip_json_fence(result.text)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            start, end = raw.find("{"), raw.rfind("}")
            if start == -1 or end <= start:
                raise NvidiaEmptyResponseError(
                    "model did not return parseable JSON", model_id=result.model_id)
            try:
                parsed = json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                raise NvidiaEmptyResponseError(
                    "model did not return parseable JSON", model_id=result.model_id) from None
        if not isinstance(parsed, dict):
            raise NvidiaEmptyResponseError(
                f"expected a JSON object, got {type(parsed).__name__}",
                model_id=result.model_id)
        parsed["_model_id"] = result.model_id
        parsed["_latency_s"] = result.latency_s
        return parsed

    # ── internals ────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_chain(
        role: ModelRole, model_id: Optional[str], pin_strict: bool = False
    ) -> List[ModelSpec]:
        chain = get_chain(role)
        if model_id is None:
            if pin_strict:
                raise ValueError("pin_strict=True requires an explicit model_id")
            return chain
        pinned = [s for s in chain if s.model_id == model_id]
        if not pinned:
            raise ValueError(
                f"model_id={model_id!r} is not registered for role {role.value!r}. "
                f"Registered: {[s.model_id for s in chain]}. "
                "Add it to registry.py with measured evidence before routing to it."
            )
        if pin_strict:
            return pinned
        # Pinned model first, the rest stay available as failover.
        return pinned + [s for s in chain if s.model_id != model_id]

    @staticmethod
    def _build_messages(
        system: Optional[str], user: str, images: Optional[Sequence[ImageInput]]
    ) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        if images:
            parts: List[Dict[str, Any]] = [{"type": "text", "text": user}]
            for img in images:
                url = img.url if isinstance(img, ImagePart) else str(img)
                parts.append({"type": "image_url", "image_url": {"url": url}})
            messages.append({"role": "user", "content": parts})
        else:
            messages.append({"role": "user", "content": user})
        return messages

    @staticmethod
    def _build_chat_payload(
        spec: ModelSpec,
        messages: List[Dict[str, Any]],
        *,
        max_tokens: Optional[int],
        temperature: Optional[float],
        extra_params: Optional[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": spec.model_id,
            "messages": messages,
            "stream": False,
            **dict(spec.params),
        }
        # Registry params are defaults; explicit call-site values win. The
        # registry's chat_template_kwargs guards are NOT overridable this way
        # on purpose — see UTILITY_JSON notes on leaked chain-of-thought.
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        payload.setdefault("max_tokens", 1024)
        if temperature is not None:
            payload["temperature"] = temperature
        if extra_params:
            for k, v in extra_params.items():
                if k in {"model", "messages", "stream", "chat_template_kwargs"}:
                    continue
                payload[k] = v
        return payload

    async def _post(
        self, url: str, key: str, payload: Mapping[str, Any], timeout_s: float
    ) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        model_id = str(payload.get("model"))
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as http:
                response = await http.post(url, headers=headers, json=dict(payload))
        except (httpx.TimeoutException, asyncio.TimeoutError) as exc:
            raise NvidiaTimeoutError(
                f"request exceeded {timeout_s}s", model_id=model_id,
                key_hint=redact(key)) from exc
        except httpx.HTTPError as exc:
            raise NvidiaProviderError(
                f"transport failure: {exc}", model_id=model_id,
                key_hint=redact(key)) from exc

        status = response.status_code
        if status == 200:
            try:
                return response.json()
            except ValueError as exc:
                raise NvidiaProviderError(
                    "response body was not JSON", model_id=model_id,
                    status=status) from exc

        body = response.text[:300]
        if status in (401, 403):
            raise NvidiaAuthError("credential rejected", model_id=model_id,
                                  status=status, key_hint=redact(key))
        if status in (429, 503):
            raise NvidiaCapacityError(f"capacity: {body}", model_id=model_id,
                                      status=status, key_hint=redact(key))
        if status == 410:
            # Definitive: NVIDIA returns a Gone document naming the EOL date.
            raise NvidiaModelGoneError(f"model end-of-life: {body}",
                                       model_id=model_id, status=status)
        if status == 404:
            # NOT definitive. Measured 2026-09-27: `meta/muse-glimmer-30b`
            # returned a single bodyless 404 between four successful 200s, so
            # a bare 404 is a routing blip and must be retried on another
            # credential. A 404 WITH a body is a real "no such model/function"
            # answer (that is how nvclip reports non-entitlement).
            if body.strip():
                raise NvidiaModelGoneError(f"model unavailable: {body}",
                                           model_id=model_id, status=status)
            raise NvidiaCapacityError("bodyless 404 (transient routing)",
                                      model_id=model_id, status=status,
                                      key_hint=redact(key))
        raise NvidiaProviderError(f"unexpected response: {body}",
                                  model_id=model_id, status=status)

    @staticmethod
    def _accept_chat(
        role: ModelRole, spec: ModelSpec, data: Mapping[str, Any],
        elapsed: float, attempts: int,
    ) -> ChatResult:
        """Validate a 200 before treating it as an answer."""
        choices = data.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            raise NvidiaEmptyResponseError("provider returned no choices",
                                           model_id=spec.model_id)
        choice = choices[0]
        message = choice.get("message") or {}
        finish = choice.get("finish_reason")
        content = (message.get("content") or "").strip()
        reasoning = message.get("reasoning_content") or ""

        if not content:
            if reasoning and finish == "length":
                cause = ("reasoning tokens consumed max_tokens before any "
                         "content was written")
            elif finish == "length":
                cause = "completion truncated at max_tokens with no content"
            else:
                cause = "provider returned empty content"
            raise NvidiaEmptyResponseError(cause, model_id=spec.model_id)

        text = _THINK_BLOCK.sub("", content).strip()
        if not text:
            raise NvidiaEmptyResponseError(
                "content contained only a reasoning block", model_id=spec.model_id)

        return ChatResult(
            text=text,
            # The SERVED model, echoed by the endpoint — never the requested id.
            model_id=str(data.get("model") or spec.model_id),
            requested_model_id=spec.model_id,
            role=role.value,
            latency_s=round(elapsed, 3),
            attempts=attempts,
            finish_reason=finish,
            usage=data.get("usage") or {},
        )

    @staticmethod
    def _exhausted(
        role: ModelRole, chain: Sequence[ModelSpec], attempts: int,
        last_error: Optional[Exception],
    ) -> NvidiaProviderError:
        logger.error(
            "nvidia_role_chain_exhausted",
            role=role.value,
            models_tried=[s.model_id for s in chain],
            attempts=attempts,
            last_error=str(last_error) if last_error else None,
            action_required=(
                "caller must degrade honestly (deterministic engine / "
                "analysis_available=False) — never synthesise a result"
            ),
        )
        return NvidiaProviderError(
            f"every NVIDIA candidate for role {role.value!r} failed after "
            f"{attempts} attempt(s); last error: {last_error}"
        )


def _strip_json_fence(text: str) -> str:
    match = _JSON_FENCE.match(text)
    return match.group(1) if match else text


#: Shared instance — import this rather than constructing per request.
nvidia_client = NvidiaClient()
