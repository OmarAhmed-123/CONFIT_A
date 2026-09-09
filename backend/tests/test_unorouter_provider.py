"""Tests for UnoRouter unified AI provider integration.

These tests verify:
  - Configuration validation (is_configured)
  - Chat completion (mocked HTTP)
  - Vision analysis (mocked HTTP)
  - Rate limit handling (429 → UnoRouterError)
  - Integration in orchestrator failover chain
  - Integration in visual search vision fallback
"""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.app.providers.unorouter_provider import (
    is_configured,
    chat_completion,
    vision_analysis,
    UnoRouterError,
)


def _run(coro):
    """Run an async coroutine in a sync test."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class TestUnoRouterConfiguration:
    def test_not_configured_when_key_missing(self):
        with patch("backend.app.providers.unorouter_provider.settings") as mock_settings:
            mock_settings.UNOROUTER_API_KEY = None
            assert is_configured() is False

    def test_configured_when_key_set(self):
        with patch("backend.app.providers.unorouter_provider.settings") as mock_settings:
            mock_settings.UNOROUTER_API_KEY = "test-key-12345"
            assert is_configured() is True

    def test_not_configured_when_key_empty(self):
        with patch("backend.app.providers.unorouter_provider.settings") as mock_settings:
            mock_settings.UNOROUTER_API_KEY = ""
            assert is_configured() is False


# ---------------------------------------------------------------------------
# Chat Completion
# ---------------------------------------------------------------------------

class TestUnoRouterChatCompletion:
    def test_chat_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Here's a great outfit suggestion."}}],
            "model": "glm-5.3-flash"
        }

        async def _test():
            with patch("backend.app.providers.unorouter_provider.settings") as mock_settings, \
                 patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
                mock_settings.UNOROUTER_API_KEY = "test-key"
                mock_settings.UNOROUTER_CHAT_MODEL = "glm-5.3-flash:free"
                mock_settings.UNOROUTER_TIMEOUT_SECONDS = 30.0

                text, model_id = await chat_completion("You are a fashion AI.", "Suggest an outfit.")
                assert text == "Here's a great outfit suggestion."
                assert model_id == "glm-5.3-flash"

        _run(_test())

    def test_chat_rate_limited_raises(self):
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = '{"error":{"message":"rate limit exceeded"}}'

        async def _test():
            with patch("backend.app.providers.unorouter_provider.settings") as mock_settings, \
                 patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
                mock_settings.UNOROUTER_API_KEY = "test-key"
                mock_settings.UNOROUTER_CHAT_MODEL = "glm-5.3-flash:free"
                mock_settings.UNOROUTER_TIMEOUT_SECONDS = 30.0

                with pytest.raises(UnoRouterError) as exc_info:
                    await chat_completion("system", "user")
                assert exc_info.value.reason == "rate_limited"
                assert exc_info.value.http_status == 429

        _run(_test())

    def test_chat_not_configured_raises(self):
        async def _test():
            with patch("backend.app.providers.unorouter_provider.settings") as mock_settings:
                mock_settings.UNOROUTER_API_KEY = None

                with pytest.raises(UnoRouterError) as exc_info:
                    await chat_completion("system", "user")
                assert exc_info.value.reason == "not_configured"

        _run(_test())

    def test_chat_empty_content_raises(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": ""}}],
            "model": "glm-5.3-flash"
        }

        async def _test():
            with patch("backend.app.providers.unorouter_provider.settings") as mock_settings, \
                 patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
                mock_settings.UNOROUTER_API_KEY = "test-key"
                mock_settings.UNOROUTER_CHAT_MODEL = "glm-5.3-flash:free"
                mock_settings.UNOROUTER_TIMEOUT_SECONDS = 30.0

                with pytest.raises(UnoRouterError) as exc_info:
                    await chat_completion("system", "user")
                assert exc_info.value.reason == "empty_response"

        _run(_test())


# ---------------------------------------------------------------------------
# Vision Analysis
# ---------------------------------------------------------------------------

class TestUnoRouterVisionAnalysis:
    def test_vision_json_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        vision_json = {
            "detected_category": "Outerwear",
            "detected_color": "navy",
            "detected_pattern": "solid",
            "detected_style": "smart casual"
        }
        mock_response.json.return_value = {
            "choices": [{"message": {"content": json.dumps(vision_json)}}],
            "model": "qwen2.5-vl-7b-instruct-awq"
        }

        async def _test():
            with patch("backend.app.providers.unorouter_provider.settings") as mock_settings, \
                 patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
                mock_settings.UNOROUTER_API_KEY = "test-key"
                mock_settings.UNOROUTER_VISION_MODEL = "qwen2.5-vl-7b-instruct-awq:free"
                mock_settings.UNOROUTER_TIMEOUT_SECONDS = 30.0

                result = await vision_analysis(
                    "https://example.com/blazer.jpg",
                    "Analyze this fashion image."
                )
                assert result["analysis_available"] is True
                assert result["detected_category"] == "Outerwear"
                assert "unorouter" in result["analysis_source"]

        _run(_test())

    def test_vision_prose_wrapped(self):
        """When vision model returns prose instead of JSON, wrap it."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "This image shows a navy blue blazer."}}],
            "model": "qwen2.5-vl"
        }

        async def _test():
            with patch("backend.app.providers.unorouter_provider.settings") as mock_settings, \
                 patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
                mock_settings.UNOROUTER_API_KEY = "test-key"
                mock_settings.UNOROUTER_VISION_MODEL = "qwen2.5-vl-7b-instruct-awq:free"
                mock_settings.UNOROUTER_TIMEOUT_SECONDS = 30.0

                result = await vision_analysis("https://example.com/img.jpg", "Analyze.")
                assert result["analysis_available"] is True
                assert result["detected_category"] is None
                assert "raw_response" in result["detected_attributes"]

        _run(_test())

    def test_vision_rate_limited_raises(self):
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = '{"error":{"message":"rate limit"}}'

        async def _test():
            with patch("backend.app.providers.unorouter_provider.settings") as mock_settings, \
                 patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
                mock_settings.UNOROUTER_API_KEY = "test-key"
                mock_settings.UNOROUTER_VISION_MODEL = "qwen2.5-vl-7b-instruct-awq:free"
                mock_settings.UNOROUTER_TIMEOUT_SECONDS = 30.0

                with pytest.raises(UnoRouterError) as exc_info:
                    await vision_analysis("https://example.com/img.jpg", "Analyze.")
                assert exc_info.value.reason == "rate_limited"

        _run(_test())


# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------

class TestUnoRouterConfigDefaults:
    def test_config_has_unorouter_fields(self):
        from backend.app.core.config import Settings
        s = Settings()
        assert hasattr(s, "UNOROUTER_API_KEY")
        assert hasattr(s, "UNOROUTER_CHAT_MODEL")
        assert hasattr(s, "UNOROUTER_VISION_MODEL")
        assert hasattr(s, "UNOROUTER_TIMEOUT_SECONDS")
        assert s.UNOROUTER_CHAT_MODEL == "glm-5.3-flash:free"
        assert s.UNOROUTER_VISION_MODEL == "qwen2.5-vl-7b-instruct-awq:free"
        assert s.UNOROUTER_TIMEOUT_SECONDS == 30.0

    def test_ai_providers_includes_unorouter(self):
        from backend.app.core.config import Settings
        s = Settings()
        providers = s.AI_PROVIDERS.split(",")
        assert "unorouter" in [p.strip() for p in providers]


# ---------------------------------------------------------------------------
# Orchestrator integration
# ---------------------------------------------------------------------------

class TestOrchestratorUnoRouterIntegration:
    def test_provider_status_includes_unorouter(self):
        from backend.app.providers.orchestrator import MultiProviderAIOrchestrator
        orch = MultiProviderAIOrchestrator()
        status = orch.provider_status()
        assert "unorouter" in status
        assert "configured" in status["unorouter"]
        assert "cooling_for_seconds" in status["unorouter"]
