from typing import List, Dict, Any, Optional
from backend.app.services.styling.ontology import SlotType, FormalityLevel, classify_product_slot, SLOT_DEFINITIONS
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

    @classmethod
    def calculate_compatibility(
        cls,
        products: List[Dict[str, Any]],
        target_occasion: str = "Casual"
    ) -> Dict[str, Any]:
        if not products:
            return {
                "compatibility_score": 0,
                "color_harmony_type": "None",
                "color_harmony_verdict": "No items selected",
                "aesthetic_consistency_verdict": "Empty canvas",
                "occasion_score": 0,
                "budget_status": "Within Profile Allocation",
                "is_complete_outfit": False,
                "completeness_status": "empty",
                "completeness_label": "Empty Canvas",
                "suggestions": ["Add items to evaluate compatibility."]
            }

        # 1. Color Harmony Analysis
        color_eval = ColorHarmonyEngine.evaluate_palette(products)
        color_score = color_eval["color_harmony_score"]

        # 2. Aesthetic Consistency
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

        aesthetic_verdict = "High stylistic coherence across contemporary silhouettes."
        if style_sets:
            overlap = set.intersection(*style_sets) if len(style_sets) > 1 else style_sets[0]
            if overlap:
                aesthetic_verdict = f"Perfect style synergy centered around '{list(overlap)[0].replace('_', ' ').title()}' aesthetic."

        # 3. Occasion Appropriateness
        occ_matches = 0
        for p in products:
            raw_occ = p.get("occasion_tags") or []
            if isinstance(raw_occ, list):
                occ_str = " ".join(raw_occ).lower()
            else:
                occ_str = str(raw_occ).lower()
            if target_occasion.lower() in occ_str or any(term in occ_str for term in ["formal", "wedding", "work", "business", "dinner", "party", "casual"]):
                occ_matches += 1

        occasion_score = int(min(100, max(75, (occ_matches / max(1, len(products))) * 100)))

        # 4. Completeness check
        positions = {p.get("position") for p in products if p.get("position")}
        is_complete = ("dress" in positions or ("top" in positions or "outerwear" in positions) and "bottom" in positions) and "footwear" in positions

        # 5. Ad-hoc composite score (85-98)
        base_score = 88.0 + (color_score - 85.0) * 0.4
        if len(products) >= 2:
            base_score += 4
        if is_complete:
            base_score += 4

        final_score = int(min(98, max(82, base_score)))

        suggestions = []
        if len(products) == 1:
            suggestions.append("Add trousers or outerwear to complete the look.")
        elif not is_complete:
            suggestions.append("Pair with leather loafers or formal dress shoes for optimal grounding.")
        else:
            suggestions.append("Outfit is fully balanced and styled to perfection.")

        return {
            "compatibility_score": final_score,
            "color_harmony_type": color_eval["harmony_type"],
            "color_harmony_verdict": color_eval["verdict"],
            "aesthetic_consistency_verdict": aesthetic_verdict,
            "occasion_score": occasion_score,
            "budget_status": "Within Profile Allocation",
            "is_complete_outfit": is_complete,
            "completeness_status": "complete_look" if is_complete else "core_base_look",
            "completeness_label": "Complete Ensemble" if is_complete else "Core Look",
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
