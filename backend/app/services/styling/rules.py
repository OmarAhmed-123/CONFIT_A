from abc import ABC, abstractmethod
from typing import List, Dict, Any
from backend.app.services.styling.color_harmony import ColorHarmonyEngine


class RuleResult:
    def __init__(self, passed: bool, score: float, penalty: float, explanation: str):
        self.passed = passed
        self.score = score
        self.penalty = penalty
        self.explanation = explanation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "penalty": self.penalty,
            "explanation": self.explanation
        }


class BaseStylingRule(ABC):
    @abstractmethod
    def evaluate(self, items: List[Dict[str, Any]], context: Dict[str, Any]) -> RuleResult:
        pass


class CategoryCompatibilityRule(BaseStylingRule):
    """Enforces category slot non-contradiction rules."""

    def evaluate(self, items: List[Dict[str, Any]], context: Dict[str, Any]) -> RuleResult:
        positions = [it.get("position") for it in items]
        slots = [it.get("slot_type") for it in items]
        titles = [it.get("product_title", "").lower() for it in items]

        # 1. Check for contradictory core layers (e.g. dress + separate trousers)
        if "dress" in positions and "bottom" in positions:
            return RuleResult(False, 0, 40, "Invalid combination: Dress cannot be worn simultaneously with separate trousers.")

        # 2. Check for conflicting footwear with formal attire
        formality = context.get("formality", "smart_casual")
        if formality in ["formal", "black_tie"]:
            if any("sneaker" in t for t in titles):
                return RuleResult(False, 20, 50, "Formality violation: Casual sneakers cannot be paired with formal wedding tailoring.")
            if any("denim" in t for t in titles) or any("jean" in t for t in titles):
                return RuleResult(False, 20, 50, "Formality violation: Denim jeans cannot be paired with formal wedding attire.")

        # 3. Check for multiple conflicting tops (e.g. T-shirt + Oxford shirt as visible primaries without outer)
        top_items = [it for it in items if it.get("position") == "top"]
        if len(top_items) > 1:
            return RuleResult(False, 50, 20, "Category conflict: Multiple top garments selected without distinct layering roles.")

        return RuleResult(True, 100, 0, "All category slots are fully compatible and non-conflicting.")


class FormalityCoherenceRule(BaseStylingRule):
    """Enforces uniform formality spread across outfit pieces."""

    def evaluate(self, items: List[Dict[str, Any]], context: Dict[str, Any]) -> RuleResult:
        target_formality_str = context.get("formality", "smart_casual")
        target_num = 4 if target_formality_str in ["formal", "black_tie"] else (3 if target_formality_str in ["cocktail", "business_formal"] else 2)

        formalities = [it.get("formality_num", target_num) for it in items]
        if not formalities:
            return RuleResult(True, 100, 0, "No items to evaluate.")

        max_f = max(formalities)
        min_f = min(formalities)
        delta = max_f - min_f

        if delta > 2:
            return RuleResult(False, 60, 25, f"Formality divergence detected (span of {delta}): pieces range from casual to high formal.")
        elif delta == 2:
            return RuleResult(True, 85, 10, "Acceptable smart-casual formality variance across tailored separates.")

        return RuleResult(True, 100, 0, "Perfect formality coherence across all items in ensemble.")


class OccasionAppropriatenessRule(BaseStylingRule):
    """Validates that items match the required event context."""

    def evaluate(self, items: List[Dict[str, Any]], context: Dict[str, Any]) -> RuleResult:
        target_occ = context.get("occasion", "Smart Casual").lower()

        matches = 0
        for it in items:
            raw_occ = it.get("occasion_tags") or []
            if isinstance(raw_occ, list):
                p_occ = " ".join(raw_occ).lower()
            else:
                p_occ = str(raw_occ).lower()

            if any(term in p_occ for term in [target_occ, "wedding", "formal", "work", "business", "dinner", "party", "casual"]):
                matches += 1

        ratio = matches / max(1, len(items))
        if ratio >= 0.7:
            return RuleResult(True, 96, 0, f"Ensemble is exceptionally curated for {context.get('occasion')}.")
        return RuleResult(True, 80, 10, f"Ensemble moderately aligns with {context.get('occasion')}.")


class CompletenessRule(BaseStylingRule):
    """Validates outfit completeness standards and generates honest labels."""

    def evaluate(self, items: List[Dict[str, Any]], context: Dict[str, Any]) -> RuleResult:
        positions = {it.get("position") for it in items}

        has_dress = "dress" in positions
        has_upper = "top" in positions or "outerwear" in positions or has_dress
        has_lower = "bottom" in positions or has_dress
        has_shoes = "footwear" in positions
        has_accessory = "accessory" in positions

        is_complete = (has_upper and has_lower and has_shoes)

        missing = []
        if not has_upper:
            missing.append("top/outerwear")
        if not has_lower:
            missing.append("trousers/bottom")
        if not has_shoes:
            missing.append("footwear")

        if is_complete:
            return RuleResult(True, 100, 0, "Look is fully complete (upper + lower + footwear).")
        else:
            return RuleResult(False, 70, 20, f"Partial look: Missing essential components ({', '.join(missing)}).")


class BudgetRule(BaseStylingRule):
    """Evaluates total price against target budget constraints."""

    def evaluate(self, items: List[Dict[str, Any]], context: Dict[str, Any]) -> RuleResult:
        budget_limit = context.get("detected_budget", 450.0)
        total_price = sum(it.get("price", 0.0) for it in items)

        if total_price <= budget_limit:
            return RuleResult(True, 100, 0, f"Total look (${total_price:.2f}) is within target budget (${budget_limit:.2f}).")
        elif total_price <= budget_limit * 1.25:
            return RuleResult(True, 88, 8, f"Total look (${total_price:.2f}) slightly exceeds budget for premium tailoring quality.")
        else:
            return RuleResult(True, 75, 15, f"Total look (${total_price:.2f}) exceeds target budget (${budget_limit:.2f}).")


class StylingRulesEngine:
    """Production Rule Execution Engine aggregating all stylistic validation checks."""

    def __init__(self):
        self.rules: List[BaseStylingRule] = [
            CategoryCompatibilityRule(),
            FormalityCoherenceRule(),
            OccasionAppropriatenessRule(),
            CompletenessRule(),
            BudgetRule()
        ]

    def evaluate_outfit(self, items: List[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, Any]:
        rule_results = []
        total_penalty = 0.0
        all_passed = True

        for rule in self.rules:
            res = rule.evaluate(items, context)
            rule_results.append(res)
            total_penalty += res.penalty
            if not res.passed and isinstance(rule, CategoryCompatibilityRule):
                all_passed = False

        # Color Harmony Check
        color_eval = ColorHarmonyEngine.evaluate_palette(items)
        color_score = color_eval["color_harmony_score"]

        # Completeness Check
        positions = {it.get("position") for it in items}
        is_complete = ("dress" in positions or ("top" in positions or "outerwear" in positions) and "bottom" in positions) and "footwear" in positions

        completeness_status = "complete_look" if is_complete else "core_base_look"
        completeness_label = "Complete Ensemble" if is_complete else "Core Base Look"

        missing_slots = []
        if not ("top" in positions or "outerwear" in positions or "dress" in positions):
            missing_slots.append("top")
        if not ("bottom" in positions or "dress" in positions):
            missing_slots.append("bottom")
        if not ("footwear" in positions):
            missing_slots.append("footwear")

        # Composite score
        base_score = 94.0 - total_penalty
        composite_score = int(min(98, max(70, (base_score * 0.7) + (color_score * 0.3))))

        return {
            "is_valid": all_passed,
            "composite_score": composite_score,
            "color_harmony_score": color_score,
            "color_harmony_type": color_eval["harmony_type"],
            "color_harmony_verdict": color_eval["verdict"],
            "is_complete": is_complete,
            "completeness_status": completeness_status,
            "completeness_label": completeness_label,
            "missing_slots": missing_slots,
            "rule_diagnostics": [r.to_dict() for r in rule_results]
        }
