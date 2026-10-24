"""IBM watsonx.ai chat client — the stylist's European LLM leg.

WHY A SEPARATE CLIENT AND NOT A ONE-LINE httpx CALL
  watsonx.ai does not accept the API key as a bearer token. Every call needs an
  IAM *access token* obtained by exchanging the key, and that token expires after
  ~60 minutes. Putting the exchange inline would mean one extra HTTPS round trip
  per styling request (~150-300 ms) and, worse, a hard failure on the hour when a
  token turns over mid-conversation. The token is therefore cached in memory and
  refreshed early.

WHAT THIS MODULE WILL NOT DO
  * It never logs, returns, or embeds the API key or the IAM token. Errors carry
    the HTTP status and IBM's own error code only.
  * It never fabricates an answer. `chat()` returns ``None`` when IBM serves no
    usable content, so the orchestrator falls through to the next real provider.
    A blank string dressed up as advice is the defect this project already fixed
    once (see `_accept_chat_completion` in providers/orchestrator.py).

VERIFIED LIVE 2026-10-24 (eu-de):
  POST /ml/v1/text/chat  model ibm/granite-4-h-small -> 200, 38 completion tokens
  POST /ml/v1/text/embeddings model ibm/granite-embedding-278m-multilingual
       -> 200, 768 dimensions (multilingual, so Arabic queries embed correctly)
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional, Tuple

import httpx

from backend.app.core.config import settings
from backend.app.core.logging import logger

IAM_TOKEN_URL = "https://iam.cloud.ibm.com/identity/token"


class WatsonxAuthError(RuntimeError):
    """The API key could not be exchanged for an IAM token."""


class WatsonxClient:
    """Caches an IAM token and calls watsonx.ai /ml/v1/text/chat."""

    def __init__(self) -> None:
        self._token: Optional[str] = None
        self._token_at: float = 0.0
        self._lock = asyncio.Lock()

    # ── configuration ────────────────────────────────────────────────────
    @staticmethod
    def _api_key() -> str:
        # settings reads IBM_CLOUD_API_KEY from the environment; the attribute
        # is optional so a deployment without watsonx simply skips this leg.
        return (getattr(settings, "IBM_CLOUD_API_KEY", None) or "").strip()

    @staticmethod
    def _project_id() -> str:
        return (getattr(settings, "WATSONX_PROJECT_ID", None) or "").strip()

    def is_configured(self) -> bool:
        """True only when every value the API requires is present.

        Deliberately strict: a partial configuration must not enter the stylist
        chain, because every request would pay an IAM round trip and then fail.
        """
        return bool(self._api_key() and self._project_id())

    def status(self) -> Dict[str, Any]:
        """Secret-free status for /health and observability."""
        return {
            "configured": self.is_configured(),
            "base_url_region": (settings.WATSONX_BASE_URL or "").split("//")[-1].split(".")[0],
            "project_configured": bool(self._project_id()),
            "model_id": settings.WATSONX_MODEL_ID,
            "token_cached": bool(self._token),
        }

    # ── IAM ──────────────────────────────────────────────────────────────
    async def _access_token(self, force: bool = False) -> str:
        """Return a valid IAM token, exchanging the API key when needed."""
        refresh_after = float(getattr(settings, "WATSONX_TOKEN_REFRESH_SECONDS", 3000.0))
        if not force and self._token and (time.time() - self._token_at) < refresh_after:
            return self._token

        async with self._lock:
            # Another coroutine may have refreshed while we waited.
            if not force and self._token and (time.time() - self._token_at) < refresh_after:
                return self._token

            key = self._api_key()
            if not key:
                raise WatsonxAuthError("IBM_CLOUD_API_KEY is not configured")

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    res = await client.post(
                        IAM_TOKEN_URL,
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                        data={
                            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                            "apikey": key,
                        },
                    )
            except httpx.HTTPError as exc:
                # Never echo the request body: it contains the key.
                raise WatsonxAuthError(f"IAM request failed: {type(exc).__name__}") from exc

            if res.status_code != 200:
                # IBM's error bodies describe the *key*, not the token, and are
                # safe to surface; the key itself is never included.
                detail = ""
                try:
                    body = res.json()
                    detail = str(body.get("errorCode") or body.get("errorMessage") or "")[:120]
                except Exception:  # noqa: BLE001
                    detail = ""
                raise WatsonxAuthError(f"IAM returned HTTP {res.status_code} {detail}".strip())

            payload = res.json()
            token = payload.get("access_token")
            if not token:
                raise WatsonxAuthError("IAM returned no access_token")

            self._token = token
            self._token_at = time.time()
            logger.info("watsonx IAM token refreshed", expires_in=payload.get("expires_in"))
            return token

    def invalidate_token(self) -> None:
        """Drop the cached token (called after an unexpected 401)."""
        self._token = None
        self._token_at = 0.0

    # ── inference ────────────────────────────────────────────────────────
    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 700,
        temperature: float = 0.7,
    ) -> Optional[Tuple[str, str]]:
        """One chat turn. Returns ``(content, model_id)`` or ``None``.

        ``None`` means "no usable answer" — the caller must fail over. Any
        configuration or auth fault raises, so the orchestrator can quarantine
        the leg instead of silently retrying it on every request.
        """
        if not self.is_configured():
            return None

        url = (
            f"{(settings.WATSONX_BASE_URL or '').rstrip('/')}"
            f"/ml/v1/text/chat?version={settings.WATSONX_API_VERSION}"
        )
        model_id = settings.WATSONX_MODEL_ID
        body = {
            "model_id": model_id,
            "project_id": self._project_id(),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "parameters": {"max_tokens": max_tokens, "temperature": temperature},
        }

        token = await self._access_token()
        for attempt in (1, 2):
            async with httpx.AsyncClient(
                timeout=float(getattr(settings, "WATSONX_TIMEOUT_SECONDS", 45.0))
            ) as client:
                res = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json=body,
                )

            if res.status_code == 401 and attempt == 1:
                # The cached token expired between the check and the call, or
                # was revoked. Refresh once, then give up honestly.
                self.invalidate_token()
                token = await self._access_token(force=True)
                continue

            res.raise_for_status()
            data = res.json()

            choices = data.get("choices") or []
            if not choices:
                logger.warn("watsonx returned no choices", model=model_id)
                return None

            message = choices[0].get("message") or {}
            content = (message.get("content") or "").strip()
            if not content:
                logger.warn("watsonx returned an empty message", model=model_id,
                            finish_reason=choices[0].get("finish_reason"))
                return None

            # Report the model IBM actually served, not the one we asked for:
            # a silent deprecation must not leave a false label on the answer.
            served = data.get("model_id") or model_id
            return content, served

        return None


#: Process-wide client. The IAM token cache is the reason this is a singleton.
watsonx_client = WatsonxClient()
