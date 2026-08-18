import pytest
from backend.app.providers.orchestrator import MultiProviderAIOrchestrator


@pytest.mark.asyncio
async def test_multi_provider_ai_orchestrator_live_or_fallback():
    orchestrator = MultiProviderAIOrchestrator()
    advice = await orchestrator.generate_styling_advice(
        prompt="I need a quiet luxury evening outfit for an art gallery opening under $400",
        user_style_tags=["Quiet Luxury", "Modern Minimalist"],
        preferred_colors=["Navy", "Beige"],
        budget_limit=400.0
    )

    assert "styling_advice_text" in advice
    assert len(advice["styling_advice_text"]) > 10
    assert "provider_used" in advice
    assert advice["occasion"] in ["Evening & Party", "Casual", "Smart Casual", "Work & Business"]
    print(f"\n[AI Orchestrator Live Test] Active Provider: {advice['provider_used']}")
    print(f"[AI Advice]: {advice['styling_advice_text']}\n")
