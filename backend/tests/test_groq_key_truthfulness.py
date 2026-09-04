"""BRD §12 / §14 — AI provider credential naming truthfulness.

The AI stylist "GROK" provider actually authenticates to **Groq**
(api.groq.com), not xAI/'Grok'. This pins the *truthful* naming behaviour:
- `GROQ_API_KEY` is the canonical credential name;
- `GROK_API_KEY` is a deprecated alias that still resolves (backward compat);
- the orchestrator's `provider_status()` and dispatch read the *resolved* key,
  so an operator setting either name enables Groq and it is reported as "groq";
- a module import with a resolved key is never re-labeled as xAI.

No real network call is made here — we only assert config resolution + the
orchestrator's configured-flags stop at the credential boundary.
"""
from __future__ import annotations

from backend.app.core.config import Settings


def test_groq_api_key_is_canonical_and_wins() -> None:
    s = Settings(GROQ_API_KEY="GROQ_PRIMARY", GROK_API_KEY="GROK_FALLBACK", _env_file=None)
    assert s.groq_api_key == "GROQ_PRIMARY"
    assert s.groq_api_key != "GROK_FALLBACK"


def test_grok_api_key_is_backward_compat_alias() -> None:
    s = Settings(GROQ_API_KEY=None, GROK_API_KEY="ONLY_OLD_ALIAS", _env_file=None)
    # Old deployments that only set the misleading name keep working.
    assert s.groq_api_key == "ONLY_OLD_ALIAS"


def test_unset_groq_resolves_to_none() -> None:
    s = Settings(GROQ_API_KEY=None, GROK_API_KEY=None, _env_file=None)
    assert s.groq_api_key is None


def test_orchestrator_provider_status_reflects_resolved_key() -> None:
    from backend.app.core.config import settings
    from backend.app.providers.orchestrator import MultiProviderAIOrchestrator

    orch = MultiProviderAIOrchestrator()
    # Monkeypatch the singleton config to a Settings with a resolved Groq key.
    orig = settings.GROQ_API_KEY
    orig_alias = settings.GROK_API_KEY
    try:
        settings.GROQ_API_KEY = "DUMMY_GROQ_KEY_TEST_ONLY"
        settings.GROK_API_KEY = ""
        status = orch.provider_status()
        assert status["groq"]["configured"] is True
        # The provider is reported by its truthful identity (groq), never xAI.
        assert "groq" in status and "grok" not in status
    finally:
        settings.GROQ_API_KEY = orig
        settings.GROK_API_KEY = orig_alias
