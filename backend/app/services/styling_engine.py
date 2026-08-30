from typing import List, Dict, Any, Optional
from backend.app.services.styling.color_harmony import ColorHarmonyEngine
from backend.app.services.styling.rules import StylingRulesEngine
from backend.app.services.styling.composer import OutfitComposer
from backend.app.services.styling.grounding import GroundingGenerator


class StylingEngine:
    """Unified Facade for the CONFIT Stylist Rules Engine & Grounded Recommendation Subsystem."""

    _composer = OutfitComposer()
    _rules_engine = StylingRulesEngine()

    @classmethod
    def parse_intent(
        cls,
        prompt: str,
        occasion_hint: Optional[str] = None,
        budget_hint: Optional[float] = None,
        user_styles: Optional[List[str]] = None,
        user_colors: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        return cls._composer.parse_intent(
            prompt=prompt,
            occasion_hint=occasion_hint,
            budget_hint=budget_hint,
            user_styles=user_styles,
            user_colors=user_colors
        )

    @classmethod
    def compose_outfits(
        cls,
        available_products: List[Any],
        intent: Dict[str, Any],
        user_profile: Optional[Any] = None,
        max_outfits: int = 2
    ) -> List[Dict[str, Any]]:
        return cls._composer.compose_outfits(
            available_products=available_products,
            intent=intent,
            user_profile=user_profile,
            max_outfits=max_outfits
        )

    # Canonical occasion keyword groups (shared by scoring + suggestions).
    _OCCASION_KEYWORDS = {
        "formal": ["formal", "black tie", "black-tie", "black_tie", "gala", "tuxedo", "wedding", "reception", "ball"],
        "work": ["work", "office", "business", "meeting", "boardroom", "interview", "corporate", "executive", "presentation"],
        "party": ["party", "dinner", "cocktail", "date", "night out", "evening", "gallery", "opening"],
        "casual": ["casual", "weekend", "brunch", "relaxed", "vacation", "resort", "travel", "summer"],
    }

    @classmethod
    def _target_occasion_keywords(cls, target_occasion: str) -> List[str]:
        to = (target_occasion or "").lower()
        kws = [to] if to else []
        for group, words in cls._OCCASION_KEYWORDS.items():
            if any(w in to for w in words) or group in to:
                kws.extend(words)
        return list({k for k in kws if k})

    @classmethod
    def calculate_compatibility(
        cls,
        products: List[Dict[str, Any]],
        target_occasion: str = "Casual"
    ) -> Dict[str, Any]:
        """Deterministic, discriminating compatibility evaluation.

        The composite score is DERIVED from the styling rules engine + real
        occasion-appropriateness measurement. It carries no artificial floor,
        so an invalid or clashing combination scores genuinely lower than a
        coherent one.
        """
        if not products:
            return {
                "compatibility_score": 0,
                "color_harmony_type": "None",
                "color_harmony_verdict": "No items selected",
                "aesthetic_consistency_verdict": "Empty canvas",
                "occasion_score": 0,
                "budget_status": "No items",
                "is_complete_outfit": False,
                "completeness_status": "empty",
                "completeness_label": "Empty Canvas",
                "suggestions": ["Add items to evaluate compatibility."]
            }

        # 1. Color harmony (honest, derived).
        color_eval = ColorHarmonyEngine.evaluate_palette(products)
        color_score = color_eval["color_harmony_score"]

        # 2. Aesthetic consistency via style-tag overlap.
        style_sets = []
        for p in products:
            raw_tags = p.get("style_tags") or []
            if isinstance(raw_tags, list):
                style_sets.append(set(raw_tags))
            elif isinstance(raw_tags, str):
                import json
                try:
                    style_sets.append(set(json.loads(raw_tags)))
                except Exception:
                    style_sets.append({raw_tags})
        aesthetic_verdict = "Mixed silhouettes with no unifying aesthetic thread."
        if style_sets:
            overlap = set.intersection(*style_sets) if len(style_sets) > 1 else style_sets[0]
            if overlap:
                aesthetic_verdict = f"Cohesive style synergy around the '{list(overlap)[0].replace('_', ' ').title()}' aesthetic."
            elif len(style_sets) > 1:
                aesthetic_verdict = "No shared style tags across pieces; aesthetic coherence is weak."

        # 3. Occasion appropriateness — honest fraction of items that genuinely
        #    match the target occasion (no floor).
        occ_keywords = cls._target_occasion_keywords(target_occasion)
        occ_matches = 0
        for p in products:
            raw_occ = p.get("occasion_tags") or []
            occ_str = " ".join(raw_occ).lower() if isinstance(raw_occ, list) else str(raw_occ).lower()
            if any(k in occ_str for k in occ_keywords):
                occ_matches += 1
        occasion_score = int(round((occ_matches / max(1, len(products))) * 100))

        # 4. Delegate category/formality/completeness/budget to the rules engine.
        context = {"formality": "smart_casual", "occasion": target_occasion, "detected_budget": 0.0}
        rules_eval = cls._rules_engine.evaluate_outfit(products, context)
        is_complete = rules_eval["is_complete"]

        # 5. Composite: rules engine composite blended with the measured occasion fit.
        final_score = int(round(min(100.0, max(0.0,
            rules_eval["composite_score"] * 0.7 + occasion_score * 0.3
        ))))

        # 6. Actionable suggestions from real diagnostics.
        suggestions = []
        for r in rules_eval.get("rule_diagnostics", []):
            if not r.get("passed"):
                suggestions.append(r.get("explanation"))
        if rules_eval.get("missing_slots"):
            suggestions.append("Add: " + ", ".join(rules_eval["missing_slots"]) + ".")
        if occasion_score < 60:
            suggestions.append(f"Only {occ_matches}/{len(products)} item(s) suit a '{target_occasion}' occasion.")
        if not suggestions:
            suggestions.append("Outfit is coherent, occasion-appropriate, and well balanced.")

        return {
            "compatibility_score": final_score,
            "color_harmony_type": color_eval["harmony_type"],
            "color_harmony_verdict": color_eval["verdict"],
            "aesthetic_consistency_verdict": aesthetic_verdict,
            "occasion_score": occasion_score,
            "budget_status": "Evaluated by styling rules",
            "is_complete_outfit": is_complete,
            "completeness_status": rules_eval["completeness_status"],
            "completeness_label": rules_eval["completeness_label"],
            "suggestions": suggestions
        }

    @classmethod
    def generate_grounded_fallback_text(
        cls,
        prompt: str,
        outfit: Dict[str, Any],
        intent: Dict[str, Any]
    ) -> str:
        return GroundingGenerator.generate_grounded_text(prompt, outfit, intent)
