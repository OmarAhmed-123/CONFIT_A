import time
import httpx
from typing import Dict, Any, List, Optional, Tuple
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
        if "402" in reason or "401" in reason:
            # Billing/auth failure alert — loud and greppable so an exhausted
            # or revoked key is visible in monitoring instead of silently
            # degrading quality via permanent fallback.
            logger.error(
                "ALERT AI PROVIDER BILLING/AUTH FAILURE",
                provider=provider_name,
                reason=reason,
                action_required="check API key validity and account billing/credit",
            )

    def provider_status(self) -> Dict[str, Any]:
        """Live status for observability: which providers have keys configured
        and which are currently quarantined (with remaining cooldown)."""
        now = time.time()
        return {
            "openai": {
                "configured": bool(settings.OPENAI_API_KEY),
                "cooling_for_seconds": max(0, round(self.cooldowns["openai"] - now, 1)) if "openai" in self.cooldowns else 0,
            },
            "groq": {
                "configured": bool(settings.groq_api_key),
                "cooling_for_seconds": max(0, round(self.cooldowns["groq"] - now, 1)) if "groq" in self.cooldowns else 0,
            },
            "gemini": {
                "configured": bool(settings.GEMINI_API_KEY),
                "cooling_for_seconds": max(0, round(self.cooldowns["gemini"] - now, 1)) if "gemini" in self.cooldowns else 0,
            },
            "nvidia": {
                "configured": bool(settings.NVIDIA_API_KEY),
                "cooling_for_seconds": max(0, round(self.cooldowns["nvidia"] - now, 1)) if "nvidia" in self.cooldowns else 0,
            },
        }


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
                # Each `_call_*` returns (content, model_id) where model_id is the
                # model the provider actually served (echoed in the response). The
                # `provider_used` label is built from that so it can never report a
                # model that was not the one invoked — previously the Groq label
                # claimed "LLaMA-3.3-70B" while `openai/gpt-oss-120b` was called.
                if provider == "nvidia" and settings.NVIDIA_API_KEY:
                    res = await self._call_nvidia_llama(system_prompt, user_prompt)
                    if self._is_usable(res):
                        text, model_id = res
                        return self._format_response(text, prompt, intent, f"NVIDIA {model_id}", selected_outfit)

                elif provider in ["nvidia2", "nemotron"] and (settings.NVIDIA_CHAT_KEY_2 or settings.NVIDIA_API_KEY):
                    res = await self._call_nvidia_nemotron(system_prompt, user_prompt)
                    if self._is_usable(res):
                        text, model_id = res
                        return self._format_response(text, prompt, intent, f"NVIDIA {model_id}", selected_outfit)

                elif provider in ["groq", "grok"] and settings.groq_api_key:
                    res = await self._call_groq(system_prompt, user_prompt)
                    if self._is_usable(res):
                        text, model_id = res
                        return self._format_response(text, prompt, intent, f"Groq {model_id}", selected_outfit)

                elif provider == "gemini" and settings.GEMINI_API_KEY:
                    res = await self._call_gemini(system_prompt, user_prompt)
                    if self._is_usable(res):
                        text, model_id = res
                        return self._format_response(text, prompt, intent, f"Google {model_id}", selected_outfit)

                elif provider == "openai" and settings.OPENAI_API_KEY:
                    res = await self._call_openai(system_prompt, user_prompt)
                    if self._is_usable(res):
                        text, model_id = res
                        return self._format_response(text, prompt, intent, f"OpenAI {model_id}", selected_outfit)

            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in [401, 402, 404, 429]:
                    self.mark_cooling(provider, f"HTTP {exc.response.status_code}")
                logger.warn(f"Provider {provider} returned HTTP error", status=exc.response.status_code)
            except Exception as exc:
                logger.warn(f"Provider {provider} failed, moving to failover", error=str(exc))

        # Deterministic Grounded Fallback Engine
        logger.info("Routing to CONFIT deterministic StylingEngine fallback")
        return self._deterministic_fallback(prompt, intent, selected_outfit)

    async def _call_nvidia_llama(self, system_prompt: str, user_prompt: str) -> Optional[Tuple[str, str]]:
        async with httpx.AsyncClient(timeout=self._timeout("chat")) as client:
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
                    "max_tokens": self._max_tokens(),
                    "temperature": 0.7
                }
            )
            res.raise_for_status()
            return self._accept_chat_completion(
                "nvidia", res.json(), "meta/llama-3.1-70b-instruct")

    async def _call_nvidia_nemotron(self, system_prompt: str, user_prompt: str) -> Optional[Tuple[str, str]]:
        async with httpx.AsyncClient(timeout=self._timeout("chat")) as client:
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
                    "max_tokens": self._max_tokens(),
                    "temperature": 0.7
                }
            )
            res.raise_for_status()
            return self._accept_chat_completion(
                "nvidia2", res.json(), "nvidia/nemotron-nano-12b-v2-vl")

    async def _call_groq(self, system_prompt: str, user_prompt: str) -> Optional[Tuple[str, str]]:
        async with httpx.AsyncClient(timeout=self._timeout("chat")) as client:
            res = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.groq_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "openai/gpt-oss-120b",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "max_tokens": self._max_tokens(),
                    "temperature": 0.7
                }
            )
            res.raise_for_status()
            return self._accept_chat_completion(
                "groq", res.json(), "openai/gpt-oss-120b")

    async def _call_gemini(self, system_prompt: str, user_prompt: str) -> Optional[Tuple[str, str]]:
        async with httpx.AsyncClient(timeout=self._timeout("gemini")) as client:
            res = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_TEXT_MODEL}:generateContent?key={settings.GEMINI_API_KEY}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{
                        "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]
                    }]
                }
            )
            res.raise_for_status()
            return self._accept_gemini_completion(res.json(), settings.GEMINI_TEXT_MODEL)

    async def _call_openai(self, system_prompt: str, user_prompt: str) -> Optional[Tuple[str, str]]:
        async with httpx.AsyncClient(timeout=self._timeout("chat")) as client:
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
                    "max_tokens": self._max_tokens()
                }
            )
            res.raise_for_status()
            return self._accept_chat_completion("openai", res.json(), "gpt-4o-mini")

    # ------------------------------------------------- response validation
    @staticmethod
    def _is_usable(res: Optional[Tuple[str, str]]) -> bool:
        """Belt-and-braces guard for the failover loop.

        `_call_*` already returns None for an empty answer, but a tuple holding
        an empty string is TRUTHY in Python - that is precisely how an empty
        answer used to slip through `if res:`. Checking it here too means a
        future provider method that forgets the validator still cannot make the
        orchestrator report an answer nobody produced.
        """
        return bool(res) and bool(res[0]) and bool(res[0].strip())

    def _timeout(self, kind: str) -> float:
        """Per-provider HTTP budget.

        One hardcoded 4.0s for every provider was wrong in both directions:
        generous for Groq (measured 0.48-0.56s live) and marginal for
        gemini-3.8-flash, a thinking model measured at 2.9s when it answers and
        >4s when it 503s. Both values are configuration, not literals.
        """
        if kind == "gemini":
            return float(getattr(settings, "GEMINI_TIMEOUT_SECONDS", 10.0) or 10.0)
        return float(getattr(settings, "AI_PROVIDER_TIMEOUT_SECONDS", 4.0) or 4.0)

    def _max_tokens(self) -> int:
        """Completion budget shared by the OpenAI-compatible providers.

        300 was tuned for a non-reasoning model. gpt-oss-120b writes
        `message.reasoning` first and it counts against the SAME budget, so 300
        regularly produced finish_reason="length" with content="" - an empty
        answer the orchestrator used to accept.
        """
        return int(getattr(settings, "AI_MAX_TOKENS", 900) or 900)

    def _accept_chat_completion(
        self, provider: str, data: Any, requested_model: str
    ) -> Optional[Tuple[str, str]]:
        """Validate an OpenAI-compatible chat completion before accepting it.

        Returns ``(content, model_id)`` or ``None``. ``None`` means "this
        provider produced no usable answer", and the caller MUST fail over to
        the next real provider - it must never return an empty string dressed
        up as AI advice under a provider label that claims a model served it.

        Why this exists (live evidence, 2026-09-04, real Groq call):
        `openai/gpt-oss-120b` is a reasoning model; two of four real
        end-to-end `generate_styling_advice` calls returned
        `styling_advice_text=""` while `provider_used` still read
        "Groq openai/gpt-oss-120b". The previous guard could not catch it
        because the fix for the model-label defect made `_call_*` return a
        TUPLE, and `("", "openai/gpt-oss-120b")` is truthy - so `if res:`
        accepted an empty answer. Truthful labelling is worthless if the thing
        labelled never existed.
        """
        if not isinstance(data, dict):
            self._log_empty(provider, requested_model, requested_model, None, 0, 0,
                            "response was not a JSON object")
            return None
        choices = data.get("choices") or []
        choice = choices[0] if choices and isinstance(choices[0], dict) else {}
        message = choice.get("message") or {}
        content = message.get("content")
        reasoning = message.get("reasoning")
        finish = choice.get("finish_reason")
        model_id = data.get("model") or requested_model

        if isinstance(content, str) and content.strip():
            return content.strip(), model_id

        content_chars = len(content) if isinstance(content, str) else 0
        reasoning_chars = len(reasoning) if isinstance(reasoning, str) else 0
        if reasoning_chars and finish == "length":
            cause = "reasoning tokens consumed max_tokens before any content was written"
        elif finish == "length":
            cause = "completion truncated at max_tokens with no content"
        elif not choices:
            cause = "provider returned no choices"
        else:
            cause = "provider returned empty content"
        self._log_empty(provider, requested_model, model_id, finish,
                        content_chars, reasoning_chars, cause)
        return None

    def _accept_gemini_completion(
        self, data: Any, requested_model: str
    ) -> Optional[Tuple[str, str]]:
        """Validate a Gemini generateContent response before accepting it.

        Two Gemini-specific traps, both observed live on 2026-09-04 against
        `gemini-flash-latest` (which currently serves `gemini-3.8-flash`):
        * a thinking model can emit parts that carry only a `thoughtSignature`
          and no `text`, so `parts[0]["text"]` either KeyErrors or reads an
          empty string - every text part must be joined;
        * thought tokens count against `maxOutputTokens`, so a "successful"
          200 can still arrive with finishReason=MAX_TOKENS and truncated or
          absent text.
        """
        if not isinstance(data, dict):
            self._log_empty("gemini", requested_model, requested_model, None, 0, 0,
                            "response was not a JSON object")
            return None
        candidates = data.get("candidates") or []
        candidate = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(
            p.get("text") or "" for p in parts if isinstance(p, dict)
        ).strip()
        model_id = data.get("modelVersion") or requested_model
        finish = candidate.get("finishReason")
        usage = data.get("usageMetadata") or {}

        if text:
            return text, model_id

        thoughts = usage.get("thoughtsTokenCount")
        if thoughts and finish == "MAX_TOKENS":
            cause = f"{thoughts} thought tokens consumed maxOutputTokens before text was written"
        elif not candidates:
            cause = "provider returned no candidates"
        else:
            cause = "provider returned no text parts"
        self._log_empty("gemini", requested_model, model_id, finish, 0,
                        int(thoughts or 0), cause)
        return None

    def _log_empty(self, provider: str, requested_model: str, model_served: Any,
                   finish_reason: Any, content_chars: int, reasoning_chars: int,
                   cause: str) -> None:
        """Loud, structured and greppable: an empty AI answer is an incident,
        not a shrug. The whole point of the failover chain is that the next
        provider gets a chance, and that only works if this is visible."""
        logger.error(
            "ai_provider_empty_response",
            provider=provider,
            requested_model=requested_model,
            model_served=str(model_served),
            finish_reason=str(finish_reason),
            content_chars=content_chars,
            reasoning_chars=reasoning_chars,
            cause=cause,
            action_required="failover to the next configured provider",
        )

    def _verify_grounding(self, ai_text: str, outfit: Optional[Dict[str, Any]]) -> bool:
        """
        C14 FIX: Styling Engine Grounding Validation.
        Verify that AI-generated text actually references real catalog products/brands.
        Prevents hallucinated products/brands/attributes.
        Returns True if grounded, False if hallucinated.
        """
        if not outfit or not outfit.get("items"):
            return True  # No outfit to ground against - fallback will handle

        text_lower = ai_text.lower()
        items = outfit["items"]

        # Check that at least 50% of brand names appear in text (or generic grounding)
        brand_matches = 0
        for item in items:
            brand = (item.get("brand_name") or "").lower()
            title = (item.get("product_title") or "").lower()
            # Check if brand or significant part of title appears
            if brand and brand in text_lower:
                brand_matches += 1
            elif title and len(title.split()) > 1:
                # Check if at least 2 words from title appear
                title_words = [w for w in title.split() if len(w) > 3]
                if sum(1 for w in title_words if w in text_lower) >= 2:
                    brand_matches += 1

        # Require at least 50% grounding or at least 1 match for small outfits
        required = max(1, len(items) // 2)
        is_grounded = brand_matches >= required

        if not is_grounded:
            logger.warn(
                "Styling grounding verification failed",
                brand_matches=brand_matches,
                required=required,
                total_items=len(items),
                ai_text_preview=ai_text[:200],
            )

        return is_grounded

    def _format_response(
        self,
        ai_text: str,
        prompt: str,
        intent: Dict[str, Any],
        provider_name: str,
        selected_outfit: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        # C14: Verify grounding before accepting AI response
        if selected_outfit and not self._verify_grounding(ai_text, selected_outfit):
            logger.info("Grounding failed, using deterministic fallback", provider=provider_name)
            return self._deterministic_fallback(prompt, intent, selected_outfit)

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

# Process-wide singleton: quarantine/cooldown state is meaningless if a fresh
# orchestrator is built per request (a dead provider would be retried every
# time, adding its timeout to every response). One shared instance makes the
# failover memory real.
_SHARED_ORCHESTRATOR: Optional["MultiProviderAIOrchestrator"] = None


def get_orchestrator() -> "MultiProviderAIOrchestrator":
    global _SHARED_ORCHESTRATOR
    if _SHARED_ORCHESTRATOR is None:
        _SHARED_ORCHESTRATOR = MultiProviderAIOrchestrator()
    return _SHARED_ORCHESTRATOR
