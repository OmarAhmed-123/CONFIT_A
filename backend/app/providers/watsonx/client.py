"""Minimal, honest watsonx.ai chat client.

Responsibilities (and nothing more):

* exchange the IBM Cloud API key for an IAM bearer token and cache it until
  shortly before expiry (tokens live 3600 s);
* call ``POST {WATSONX_URL}/ml/v1/text/chat?version=…`` with the tutorial's
  message format (text and ``image_url`` data-URL parts);
* classify failures so callers can react: not-configured, auth, model
  unsupported, rate limit, timeout, transport, malformed response;
* retry ONLY transient classes (429 / 5xx / timeout) with capped backoff;
* never log or raise the api key, the bearer token, or the image payload.

Everything that interprets model output lives in the callers.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from backend.app.core.config import settings
from backend.app.core.logging import logger

IAM_TOKEN_URL = "https://iam.cloud.ibm.com/identity/token"
_USER_AGENT = "confit-stylist/1.0 (+https://github.com/OmarAhmed-123/CONFIT_A)"
# Refresh the IAM token this many seconds before IBM says it expires.
_TOKEN_SAFETY_MARGIN_S = 120.0


class WatsonxError(Exception):
    """Base class. ``code`` is a stable, user-safe identifier; ``retryable``
    tells the caller whether an identical retry could plausibly succeed."""

    code = "watsonx_error"
    retryable = False

    def __init__(self, message: str = "", *, status: Optional[int] = None, trace: Optional[str] = None):
        super().__init__(message or self.code)
        self.status = status
        self.trace = trace


class WatsonxNotConfiguredError(WatsonxError):
    code = "watsonx_not_configured"


class WatsonxAuthError(WatsonxError):
    code = "watsonx_auth_failed"


class WatsonxModelUnsupportedError(WatsonxError):
    code = "watsonx_model_not_supported"


class WatsonxRateLimitError(WatsonxError):
    code = "watsonx_rate_limited"
    retryable = True


class WatsonxTimeoutError(WatsonxError):
    code = "watsonx_timeout"
    retryable = True


class WatsonxTransportError(WatsonxError):
    code = "watsonx_unreachable"
    retryable = True


class WatsonxBadResponseError(WatsonxError):
    code = "watsonx_invalid_response"


@dataclass
class WatsonxChatResult:
    content: str
    model_id: str
    usage: Dict[str, Any] = field(default_factory=dict)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    latency_seconds: float = 0.0
    finish_reason: Optional[str] = None


def watsonx_configured() -> bool:
    """True only when every credential the tutorial requires is present."""
    return bool(settings.WATSONX_APIKEY and settings.WATSONX_PROJECT_ID and settings.WATSONX_URL)


def redact(value: Optional[str]) -> str:
    """Last-4 redaction for log lines (never the key itself)."""
    if not value:
        return "<unset>"
    return f"…{value[-4:]}" if len(value) > 8 else "<set>"


class WatsonxClient:
    """One instance per process is enough; the IAM token is cached on it."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        project_id: Optional[str] = None,
        url: Optional[str] = None,
        api_version: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        max_retries: Optional[int] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self._api_key = api_key if api_key is not None else settings.WATSONX_APIKEY
        self._project_id = project_id if project_id is not None else settings.WATSONX_PROJECT_ID
        self._url = (url if url is not None else settings.WATSONX_URL or "").rstrip("/")
        self._api_version = api_version or settings.WATSONX_API_VERSION
        self._timeout = float(timeout_seconds if timeout_seconds is not None else settings.WATSONX_TIMEOUT_SECONDS)
        self._max_retries = max(0, int(max_retries if max_retries is not None else settings.WATSONX_MAX_RETRIES))
        self._transport = transport  # tests inject httpx.MockTransport
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

    # ── configuration ────────────────────────────────────────────────
    @property
    def configured(self) -> bool:
        return bool(self._api_key and self._project_id and self._url)

    @property
    def url(self) -> str:
        return self._url

    def _require_configured(self) -> None:
        if not self.configured:
            missing = [
                name for name, val in (
                    ("WATSONX_APIKEY", self._api_key),
                    ("WATSONX_PROJECT_ID", self._project_id),
                    ("WATSONX_URL", self._url),
                ) if not val
            ]
            raise WatsonxNotConfiguredError(f"watsonx.ai is not configured (missing: {', '.join(missing)})")

    def _http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout, connect=10.0),
            headers={"User-Agent": _USER_AGENT},
            transport=self._transport,
        )

    # ── IAM ──────────────────────────────────────────────────────────
    async def _bearer_token(self, *, force: bool = False) -> str:
        async with self._token_lock:
            if not force and self._token and time.time() < self._token_expires_at:
                return self._token
            try:
                async with self._http() as client:
                    resp = await client.post(
                        getattr(settings, "WATSONX_IAM_URL", None) or IAM_TOKEN_URL,
                        data={"grant_type": "urn:ibm:params:oauth:grant-type:apikey", "apikey": self._api_key},
                        headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
                    )
            except httpx.TimeoutException as exc:
                raise WatsonxTimeoutError("IAM token request timed out") from exc
            except httpx.HTTPError as exc:
                raise WatsonxTransportError("IAM endpoint unreachable") from exc
            if resp.status_code in (400, 401, 403):
                logger.error("watsonx_iam_rejected", status=resp.status_code, apikey=redact(self._api_key))
                raise WatsonxAuthError("IBM Cloud rejected the API key", status=resp.status_code)
            if resp.status_code >= 500:
                raise WatsonxTransportError("IAM service error", status=resp.status_code)
            try:
                body = resp.json()
                token = body["access_token"]
                expires_in = float(body.get("expires_in", 3600))
            except (ValueError, KeyError, TypeError) as exc:
                raise WatsonxBadResponseError("IAM response malformed") from exc
            self._token = token
            self._token_expires_at = time.time() + max(60.0, expires_in - _TOKEN_SAFETY_MARGIN_S)
            return token

    # ── chat ─────────────────────────────────────────────────────────
    async def chat(
        self,
        *,
        model_id: str,
        messages: List[Dict[str, Any]],
        max_tokens: int = 600,
        temperature: float = 0.0,
        response_json: bool = False,
        deployment_id: Optional[str] = None,
    ) -> WatsonxChatResult:
        """``ModelInference.chat`` equivalent. Raises a ``WatsonxError`` subclass
        on failure; transient classes are retried up to ``max_retries`` times.

        ``deployment_id`` targets a *deploy-on-demand* model (dedicated
        hardware, hourly billing) via ``/ml/v1/deployments/{id}/text/chat``.
        IBM serves the Granite Vision family (``granite-vision-3-3-2b``,
        ``granite-vision-4-1-4b``) **only** this way as of 2026-10 — they are
        not in the pay-per-token multitenant catalog of any region (verified
        live: 404 ``model_not_supported`` in eu-de). For a deployment call the
        REST contract omits ``model_id``/``project_id``; the served model id
        is still read back from the response so provenance stays truthful.
        """
        self._require_configured()
        body: Dict[str, Any] = {
            "messages": messages,
            "max_tokens": int(max_tokens),
            "temperature": float(temperature),
        }
        if deployment_id:
            endpoint = f"{self._url}/ml/v1/deployments/{deployment_id}/text/chat?version={self._api_version}"
            _label = model_id or f"deployment:{deployment_id}"
        else:
            body["model_id"] = model_id
            body["project_id"] = self._project_id
            endpoint = f"{self._url}/ml/v1/text/chat?version={self._api_version}"
            _label = model_id
        if response_json:
            # Supported by the chat API for JSON-mode capable models; harmless
            # (ignored) otherwise. Output is still validated by the caller.
            body["response_format"] = {"type": "json_object"}

        attempt = 0
        last_exc: Optional[WatsonxError] = None
        while attempt <= self._max_retries:
            attempt += 1
            started = time.time()
            try:
                return await self._chat_once(endpoint, body, started, _label)
            except WatsonxAuthError as exc:
                # One forced token refresh covers an expired cached token;
                # a second 401 is a real credential problem.
                if attempt == 1 and exc.status == 401:
                    self._token = None
                    last_exc = exc
                    continue
                raise
            except WatsonxError as exc:
                last_exc = exc
                if not exc.retryable or attempt > self._max_retries:
                    raise
                backoff = min(4.0, 0.5 * (2 ** (attempt - 1)))
                logger.warn("watsonx_retry", code=exc.code, attempt=attempt, backoff=backoff, model_id=model_id)
                await asyncio.sleep(backoff)
        assert last_exc is not None
        raise last_exc

    async def _chat_once(self, endpoint: str, body: Dict[str, Any], started: float, label: str = "") -> WatsonxChatResult:
        token = await self._bearer_token()
        try:
            async with self._http() as client:
                resp = await client.post(
                    endpoint,
                    json=body,
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                )
        except httpx.TimeoutException as exc:
            logger.warn("watsonx_timeout", model_id=(body.get("model_id") or label), timeout=self._timeout)
            raise WatsonxTimeoutError("watsonx.ai request timed out") from exc
        except httpx.HTTPError as exc:
            logger.warn("watsonx_unreachable", model_id=(body.get("model_id") or label), error=type(exc).__name__)
            raise WatsonxTransportError("watsonx.ai unreachable") from exc

        status = resp.status_code
        if status == 401 or status == 403:
            raise WatsonxAuthError("watsonx.ai rejected the credentials or project", status=status)
        if status == 404:
            detail = _error_detail(resp)
            if "model_not_supported" in detail or "model" in detail.lower():
                logger.error("watsonx_model_not_supported", model_id=(body.get("model_id") or label), detail=detail[:200])
                raise WatsonxModelUnsupportedError(
                    f"Model '{body['model_id']}' is not available on this watsonx.ai region "
                    "(deprecated, removed, or not enabled for the project)",
                    status=status,
                )
            raise WatsonxBadResponseError(f"watsonx.ai endpoint not found: {detail[:120]}", status=status)
        if status == 429:
            raise WatsonxRateLimitError("watsonx.ai rate limit reached", status=status)
        if status >= 500:
            raise WatsonxTransportError("watsonx.ai service error", status=status)
        if status != 200:
            raise WatsonxBadResponseError(f"watsonx.ai HTTP {status}: {_error_detail(resp)[:160]}", status=status)

        try:
            data = resp.json()
            choice = data["choices"][0]
            content = choice["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise WatsonxBadResponseError("watsonx.ai response missing choices[0].message.content") from exc
        if isinstance(content, list):
            # Some multimodal models return content parts; flatten text parts.
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        if not isinstance(content, str):
            raise WatsonxBadResponseError("watsonx.ai message content is not text")

        warnings = []
        sys_block = data.get("system") if isinstance(data.get("system"), dict) else {}
        for w in sys_block.get("warnings", []) or []:
            if isinstance(w, dict):
                warnings.append({"id": w.get("id"), "message": str(w.get("message", ""))[:200]})
                if w.get("id") in ("deprecation_warning", "withdrawn_warning"):
                    logger.warn("watsonx_model_lifecycle_warning", model_id=(body.get("model_id") or label), warning=w.get("id"))
        return WatsonxChatResult(
            content=content,
            model_id=str(data.get("model_id") or (body.get("model_id") or label)),
            usage=data.get("usage") or {},
            warnings=warnings,
            latency_seconds=round(time.time() - started, 3),
            finish_reason=choice.get("finish_reason"),
        )


def _error_detail(resp: httpx.Response) -> str:
    try:
        j = resp.json()
        errs = j.get("errors")
        if isinstance(errs, list) and errs:
            e = errs[0]
            return f"{e.get('code', '')}: {e.get('message', '')}"
        return str(j.get("detail") or j)[:300]
    except ValueError:
        return resp.text[:300]


_client_singleton: Optional[WatsonxClient] = None


def get_watsonx_client() -> WatsonxClient:
    """Process-wide client (IAM token cache). Tests construct their own."""
    global _client_singleton
    if _client_singleton is None or not _client_singleton.configured:
        _client_singleton = WatsonxClient()
    return _client_singleton


def reset_watsonx_client() -> None:
    global _client_singleton
    _client_singleton = None
