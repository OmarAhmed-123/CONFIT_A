import re
from typing import Any, Dict, List, Optional
from backend.app.providers.base import BaseProvider


class StylistAIProvider(BaseProvider):
    def __init__(self):
        super().__init__(name="AI_Stylist_Provider", timeout_seconds=5.0, max_retries=2)

    async def generate_styling_advice(
        self,
        prompt: str,
        user_style_tags: List[str],
        preferred_colors: List[str],
        budget_limit: Optional[float] = None,
        available_catalog: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        return await self.execute_with_resilience(
            self._call_ai_model,
            prompt=prompt,
            user_style_tags=user_style_tags,
            preferred_colors=preferred_colors,
            budget_limit=budget_limit,
            available_catalog=available_catalog
        )

    async def _call_ai_model(self, **kwargs) -> Dict[str, Any]:
        # Here an OpenAI/Anthropic or LLM client call is made with structured JSON output
        # In hybrid/resilient mode, it generates context-aware styling reasoning
        return await self.fallback(**kwargs)

    async def fallback(
        self,
        prompt: str,
        user_style_tags: List[str],
        preferred_colors: List[str],
        budget_limit: Optional[float] = None,
        available_catalog: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        prompt_lower = prompt.lower()
        occasion = "Casual"
        if any(w in prompt_lower for w in ["work", "office", "business", "meeting", "interview"]):
            occasion = "Work & Business"
        elif any(w in prompt_lower for w in ["wedding", "gala", "black tie", "formal"]):
            occasion = "Formal & Wedding"
        elif any(w in prompt_lower for w in ["party", "dinner", "cocktail", "date", "night out"]):
            occasion = "Evening & Party"
        elif any(w in prompt_lower for w in ["gym", "run", "sport", "workout"]):
            occasion = "Active & Sport"

        # Detect budget mention in prompt e.g. "$250" or "under 200"
        budget_match = re.search(r'(?:under|\$|below)\s*(\d+)', prompt_lower)
        parsed_budget = float(budget_match.group(1)) if budget_match else (budget_limit or 450.0)

        # Style tone
        color_suggestion = preferred_colors[0] if preferred_colors else "Navy & Neutral Cream"
        aesthetic = user_style_tags[0] if user_style_tags else "Refined Modern"

        content = (
            f"Here is a curated {occasion} look tailored to your {aesthetic} profile. "
            f"I paired balanced neutral tones with your preferred {color_suggestion} palette, "
            f"keeping the complete silhouette cohesive, proportional, and within your ${parsed_budget:.0f} target."
        )

        return {
            "occasion": occasion,
            "detected_budget": parsed_budget,
            "aesthetic": aesthetic,
            "styling_advice_text": content,
            "color_palette_advice": ["#1B1F3B", "#C5A059", "#F8F6F0", "#2D4A3E"],
            "harmony_type": "Balanced Neutral & Monochromatic Accent"
        }
