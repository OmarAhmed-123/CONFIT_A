import time
import json
import httpx
from typing import Dict, Any, List, Optional
from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.services.styling_engine import StylingEngine


class MultiProviderAIOrchestrator:
    """Production Multi-Provider AI Orchestrator implementing live failover across NVIDIA, Groq, Gemini, and OpenAI."""

    def __init__(self):
        self.cooldowns: Dict[str, float] = {}
        self.cooldown_duration = settings.CHAT_COOLDOWN_MS / 1000.0  # default cooldown

    def is_provider_available(self, provider_name: str) -> bool:
        if provider_name in self.cooldowns:
            if time.time() < self.cooldowns[provider_name]:
                return False
            else:
                del self.cooldowns[provider_name]
        return True

    def mark_cooling(self, provider_name: str, reason: str = "Quota/Error"):
        self.cooldowns[provider_name] = time.time() + self.cooldown_duration
        logger.warn("Quarantining AI provider", provider=provider_name, reason=reason, cooldown_seconds=self.cooldown_duration)

    async def generate_styling_advice(
        self,
        prompt: str,
        user_style_tags: Optional[List[str]] = None,
        preferred_colors: Optional[List[str]] = None,
        budget_limit: Optional[float] = None,
        selected_outfit: Optional[Dict[str, Any]] = None,
        intent: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Orchestrates live AI stylist requests grounded strictly in selected outfit products."""
        user_styles = user_style_tags or ["Smart Casual", "Quiet Luxury"]
        user_colors = preferred_colors or ["Navy", "Beige", "Black"]

        if not intent:
            intent = StylingEngine.parse_intent(prompt, budget_hint=budget_limit, user_styles=user_styles, user_colors=user_colors)

        occasion = intent.get("occasion", "Smart Casual")
        detected_budget = intent.get("detected_budget", budget_limit or 450.0)
        aesthetic = intent.get("aesthetic", user_styles[0] if user_styles else "Quiet Luxury")

        # Build grounded item summary for prompt
        grounded_lines = []
        if selected_outfit and selected_outfit.get("items"):
            for item in selected_outfit["items"]:
                grounded_lines.append(f"- {item.get('position', 'Item').capitalize()}: {item.get('product_title')} by {item.get('brand_name')} in {item.get('color_family', item.get('color_hex'))} (${item.get('price', 0):.2f})")

        grounded_context = "\n".join(grounded_lines) if grounded_lines else "Curated multi-brand luxury ensemble."
        total_price = selected_outfit.get("total_price", detected_budget) if selected_outfit else detected_budget

        system_prompt = (
            "You are CONFIT's Senior AI Fashion Director. Your mission is to provide personalized, sophisticated styling guidance. "
            "IMPORTANT: Your response must be strictly grounded in the exact selected items below. Explicitly reference the chosen products, "
            "their brand names, colors, and how they harmonize for the target occasion. Keep the tone refined, warm, and concise (2-3 sentences max)."
        )
        user_prompt = (
            f"User Prompt: '{prompt}'\n"
            f"Target Occasion: {occasion}\n"
            f"Aesthetic: {aesthetic}\n"
            f"Total Look Price: ${total_price:.2f}\n"
            f"Selected Recommended Items:\n{grounded_context}\n"
            f"Explain why these exact items work together perfectly for this occasion."
        )

        providers = [p.strip().lower() for p in settings.AI_PROVIDERS.split(",") if p.strip()]

        for provider in providers:
            if not self.is_provider_available(provider):
                continue

            try:
                if provider == "nvidia" and settings.NVIDIA_API_KEY:
                    res = await self._call_nvidia_llama(system_prompt, user_prompt)
                    if res:
                        return self._format_response(res, prompt, intent, "NVIDIA Llama-3.1-70B", selected_outfit)

                elif provider in ["nvidia2", "nemotron"] and (settings.NVIDIA_CHAT_KEY_2 or settings.NVIDIA_API_KEY):
                    res = await self._call_nvidia_nemotron(system_prompt, user_prompt)
                    if res:
                        return self._format_response(res, prompt, intent, "NVIDIA Nemotron-12B", selected_outfit)

                elif provider in ["groq", "grok"] and settings.GROK_API_KEY:
                    res = await self._call_groq(system_prompt, user_prompt)
                    if res:
                        return self._format_response(res, prompt, intent, "Groq LLaMA-3.3-70B", selected_outfit)

                elif provider == "gemini" and settings.GEMINI_API_KEY:
                    res = await self._call_gemini(system_prompt, user_prompt)
                    if res:
                        return self._format_response(res, prompt, intent, "Google Gemini-Flash", selected_outfit)

                elif provider == "openai" and settings.OPENAI_API_KEY:
                    res = await self._call_openai(system_prompt, user_prompt)
                    if res:
                        return self._format_response(res, prompt, intent, "OpenAI GPT-4o-mini", selected_outfit)

            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in [401, 402, 404, 429]:
                    self.mark_cooling(provider, f"HTTP {exc.response.status_code}")
                logger.warn(f"Provider {provider} returned HTTP error", status=exc.response.status_code)
            except Exception as exc:
                logger.warn(f"Provider {provider} failed, moving to failover", error=str(exc))

        # Deterministic Grounded Fallback Engine
        logger.info("Routing to CONFIT deterministic StylingEngine fallback")
        return self._deterministic_fallback(prompt, intent, selected_outfit)

    async def _call_nvidia_llama(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        async with httpx.AsyncClient(timeout=4.0) as client:
            res = await client.post(
                "https://integrate.api.nvidia.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.NVIDIA_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "meta/llama-3.1-70b-instruct",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "max_tokens": 300,
                    "temperature": 0.7
                }
            )
            res.raise_for_status()
            return res.json()["choices"][0]["message"]["content"]

    async def _call_nvidia_nemotron(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        async with httpx.AsyncClient(timeout=4.0) as client:
            res = await client.post(
                "https://integrate.api.nvidia.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.NVIDIA_CHAT_KEY_2 or settings.NVIDIA_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "nvidia/nemotron-nano-12b-v2-vl",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "max_tokens": 300,
                    "temperature": 0.7
                }
            )
            res.raise_for_status()
            return res.json()["choices"][0]["message"]["content"]

    async def _call_groq(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        async with httpx.AsyncClient(timeout=4.0) as client:
            res = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.GROK_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "openai/gpt-oss-120b",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "max_tokens": 300,
                    "temperature": 0.7
                }
            )
            res.raise_for_status()
            return res.json()["choices"][0]["message"]["content"]

    async def _call_gemini(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        async with httpx.AsyncClient(timeout=4.0) as client:
            res = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={settings.GEMINI_API_KEY}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{
                        "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]
                    }]
                }
            )
            res.raise_for_status()
            return res.json()["candidates"][0]["content"]["parts"][0]["text"]

    async def _call_openai(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        async with httpx.AsyncClient(timeout=4.0) as client:
            res = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "max_tokens": 300
                }
            )
            res.raise_for_status()
            return res.json()["choices"][0]["message"]["content"]

    def _format_response(
        self,
        ai_text: str,
        prompt: str,
        intent: Dict[str, Any],
        provider_name: str,
        selected_outfit: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        return {
            "occasion": intent.get("occasion", "Smart Casual"),
            "detected_budget": intent.get("detected_budget", 400.0),
            "aesthetic": intent.get("aesthetic", "Quiet Luxury"),
            "styling_advice_text": ai_text.strip(),
            "color_palette_advice": selected_outfit.get("color_palette", ["#1B1F3B", "#C5A059", "#FAF9F6", "#111111"]) if selected_outfit else ["#1B1F3B", "#C5A059", "#FAF9F6", "#111111"],
            "harmony_type": "Complementary Balanced Contrast",
            "provider_used": provider_name
        }

    def _deterministic_fallback(
        self,
        prompt: str,
        intent: Dict[str, Any],
        selected_outfit: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        if selected_outfit:
            content = StylingEngine.generate_grounded_fallback_text(prompt, selected_outfit, intent)
        else:
            occasion = intent.get("occasion", "Smart Casual")
            aesthetic = intent.get("aesthetic", "Quiet Luxury")
            content = (
                f"Here is a curated {occasion} look tailored to your {aesthetic} profile. "
                f"I paired balanced neutral tones with tailored silhouettes, "
                f"keeping the complete outfit cohesive, proportional, and within your target budget."
            )

        return {
            "occasion": intent.get("occasion", "Smart Casual"),
            "detected_budget": intent.get("detected_budget", 400.0),
            "aesthetic": intent.get("aesthetic", "Quiet Luxury"),
            "styling_advice_text": content,
            "color_palette_advice": selected_outfit.get("color_palette", ["#1B1F3B", "#C5A059", "#FAF9F6", "#111111"]) if selected_outfit else ["#1B1F3B", "#C5A059", "#FAF9F6", "#111111"],
            "harmony_type": "Balanced Neutral & Monochromatic Accent",
            "provider_used": "CONFIT Grounded Styling Engine (Grounded & Resilient)"
        }
