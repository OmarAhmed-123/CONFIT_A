"""UnoRouter unified AI provider — OpenAI-compatible gateway to multiple models.

UnoRouter (api.unorouter.com) is a unified API that routes to many models
(Gemini, GLM, DeepSeek, Qwen, LLaMA, etc.) through a single OpenAI-compatible
endpoint. Free-tier models have a rate limit of ~1 request/minute per account.

Integration strategy:
  - Text/chat: added as an additional provider in the MultiProviderAIOrchestrator
    failover chain. Positioned AFTER the existing direct providers (NVIDIA, Groq,
    Gemini, OpenAI) so it serves as a cost-free fallback.
  - Vision: added as an additional fallback in VisualSearchAIProvider after
    Gemini and Qwen Vision Worker.
  - Rate limiting: 429 responses are handled gracefully with cooldown marking,
    identical to the existing provider quarantine pattern.

Configuration:
  UNOROUTER_API_KEY         — API key (required to enable)
  UNOROUTER_CHAT_MODEL      — text model (default: glm-5.3-flash:free)
  UNOROUTER_VISION_MODEL    — vision model (default: qwen2.5-vl-7b-instruct-awq:free)
  UNOROUTER_TIMEOUT_SECONDS — HTTP timeout (default: 30.0)
"""
from __future__ import annotations

import json as _json
from typing import Any, Dict, List, Optional, Tuple

import httpx

from backend.app.core.config import settings
from backend.app.core.logging import logger

_BASE_URL = "https://api.unorouter.com/v1"
_USER_AGENT = "CONFIT-UnoRouter/1.0"


class UnoRouterError(Exception):
    """Raised when UnoRouter returns an unusable response."""

    def __init__(self, reason: str, message: str = "", http_status: int = 0):
        self.reason = reason
        self.message = message
        self.http_status = http_status
        super().__init__(f"[{reason}] {message}")


def is_configured() -> bool:
    """True when UNOROUTER_API_KEY is set."""
    return bool(getattr(settings, "UNOROUTER_API_KEY", None))


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.UNOROUTER_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": _USER_AGENT,
    }


def _timeout() -> float:
    return float(getattr(settings, "UNOROUTER_TIMEOUT_SECONDS", 30.0) or 30.0)


async def chat_completion(
    system_prompt: str,
    user_prompt: str,
    *,
    model: Optional[str] = None,
    max_tokens: int = 500,
    temperature: float = 0.7,
) -> Tuple[str, str]:
    """Call UnoRouter chat completion. Returns (content, model_id).

    Raises UnoRouterError on failure. The caller (orchestrator) handles
    rate-limiting via its existing cooldown mechanism.
    """
    if not is_configured():
        raise UnoRouterError("not_configured", "UNOROUTER_API_KEY is not set")

    target_model = model or getattr(settings, "UNOROUTER_CHAT_MODEL", "glm-5.3-flash:free") or "glm-5.3-flash:free"

    payload = {
        "model": target_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    async with httpx.AsyncClient(timeout=_timeout()) as client:
        try:
            res = await client.post(
                f"{_BASE_URL}/chat/completions",
                headers=_headers(),
                json=payload,
            )
        except httpx.TimeoutException as exc:
            raise UnoRouterError("timeout", f"request timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            raise UnoRouterError("network_error", f"HTTP error: {exc}") from exc

    if res.status_code == 429:
        raise UnoRouterError("rate_limited", "UnoRouter free-tier rate limit exceeded", http_status=429)
    if res.status_code == 402:
        raise UnoRouterError("quota_exhausted", "UnoRouter quota exhausted", http_status=402)
    if res.status_code >= 400:
        body = res.text[:300]
        raise UnoRouterError("api_error", f"HTTP {res.status_code}: {body}", http_status=res.status_code)

    data = res.json()
    if not isinstance(data, dict):
        raise UnoRouterError("invalid_response", "response is not a JSON object")

    choices = data.get("choices") or []
    choice = choices[0] if choices and isinstance(choices[0], dict) else {}
    message = choice.get("message") or {}
    content = message.get("content")
    actual_model = data.get("model") or target_model

    if isinstance(content, str) and content.strip():
        return content.strip(), actual_model

    raise UnoRouterError("empty_response", "UnoRouter returned empty content")


async def vision_analysis(
    image_url_or_base64: str,
    prompt: str,
    *,
    model: Optional[str] = None,
    max_tokens: int = 300,
) -> Dict[str, Any]:
    """Vision analysis via UnoRouter multimodal models.

    Returns the same Gemini-compatible flat dict used by the rest of the
    visual search pipeline. Raises UnoRouterError on failure.
    """
    if not is_configured():
        raise UnoRouterError("not_configured", "UNOROUTER_API_KEY is not set")

    target_model = model or getattr(settings, "UNOROUTER_VISION_MODEL", "qwen2.5-vl-7b-instruct-awq:free") or "qwen2.5-vl-7b-instruct-awq:free"

    # Build multimodal message content
    if image_url_or_base64.startswith("data:image"):
        # Already a data URL — use as-is for image_url
        image_ref = image_url_or_base64
    elif image_url_or_base64.startswith(("http://", "https://")):
        image_ref = image_url_or_base64
    else:
        # Assume base64 without data URL prefix
        image_ref = f"data:image/jpeg;base64,{image_url_or_base64}"

    payload = {
        "model": target_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_ref}},
                ],
            }
        ],
        "max_tokens": max_tokens,
    }

    async with httpx.AsyncClient(timeout=_timeout()) as client:
        try:
            res = await client.post(
                f"{_BASE_URL}/chat/completions",
                headers=_headers(),
                json=payload,
            )
        except httpx.TimeoutException as exc:
            raise UnoRouterError("timeout", f"vision request timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            raise UnoRouterError("network_error", f"HTTP error: {exc}") from exc

    if res.status_code == 429:
        raise UnoRouterError("rate_limited", "UnoRouter free-tier rate limit", http_status=429)
    if res.status_code >= 400:
        raise UnoRouterError("api_error", f"HTTP {res.status_code}: {res.text[:200]}", http_status=res.status_code)

    data = res.json()
    choices = data.get("choices") or []
    choice = choices[0] if choices and isinstance(choices[0], dict) else {}
    message = choice.get("message") or {}
    content = (message.get("content") or "").strip()
    actual_model = data.get("model") or target_model

    if not content:
        raise UnoRouterError("empty_response", "UnoRouter vision returned empty content")

    # Try to parse as JSON (the vision prompt asks for JSON)
    try:
        parsed = _json.loads(content)
        parsed["analysis_available"] = True
        parsed["analysis_source"] = f"unorouter/{actual_model}"
        return parsed
    except _json.JSONDecodeError:
        # Some vision models return prose instead of JSON — wrap it
        return {
            "analysis_available": True,
            "analysis_source": f"unorouter/{actual_model}",
            "detected_category": None,
            "detected_color": None,
            "detected_pattern": None,
            "detected_style": None,
            "detected_attributes": {"raw_response": content[:500]},
        }
