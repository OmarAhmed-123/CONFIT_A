import re
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any, Optional
from backend.app.core.money import to_decimal, to_float, money_sum, quantize_money
from backend.app.services.styling.ontology import SlotType, classify_product_slot
from backend.app.services.styling.rules import StylingRulesEngine


# Common English filler words — recognizable language, but they carry NO
# styling signal. A prompt made up solely of these (or of gibberish) is
# ambiguous (BRD 2.13: "something nice" / "something stylish" must clarify).
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "for", "with", "me", "my", "i",
    "need", "want", "get", "give", "find", "something", "anything", "nice",
    "good", "some", "please", "can", "you", "to", "of", "in", "on", "at",
    "is", "it", "this", "that", "outfit", "look", "wear", "up", "help",
    "style", "stylish", "fashion", "fashionable", "cool", "great", "best",
}

# Signal-bearing styling vocabulary: occasions, garments/categories, colors,
# materials, formality and aesthetic descriptors. Gibberish tokens (e.g.
# "asdfqwer") and pure filler prompts match NONE of these -> ambiguous.
# Deliberately excludes filler ("nice", "good", "stylish") so vague praise
# words alone never count as intent.
_SIGNAL_VOCAB = {
    # Occasions
    "wedding", "gala", "formal", "casual", "work", "office", "business", "party",
    "dinner", "cocktail", "evening", "weekend", "brunch", "vacation", "resort",
    "summer", "travel", "meeting", "interview", "corporate", "date", "bride",
    "groom", "reception", "ball", "guest",
    # Garments / categories
    "dress", "suit", "blazer", "trousers", "shirt", "shoes", "oxford", "loafer",
    "gown", "maxi", "tuxedo", "heels", "sandals", "clutch", "bag", "watch",
    "tie", "belt", "jacket", "coat", "skirt", "jeans", "denim", "sneakers", "boots",
    # Colors
    "navy", "black", "white", "ivory", "red", "blue", "green", "beige", "grey",
    "gray", "brown", "gold", "silver", "pink", "burgundy", "camel", "charcoal",
    # Materials
    "silk", "linen", "cotton", "wool", "leather", "cashmere", "satin", "velvet",
    # Formality / aesthetics / context
    "tailored", "minimal", "minimalist", "classic", "modern", "contemporary",
    "monochrome", "monochromatic", "tonal", "elegant", "chic", "sharp",
    "luxury", "hot", "cold", "weather", "rain", "winter",
}


class OutfitComposer:
    """Production Multi-Brand Outfit Recommendation & Slot Composition Engine."""

    def __init__(self):
        self.rules_engine = StylingRulesEngine()

    def parse_intent(
        self,
        prompt: str,
        occasion_hint: Optional[str] = None,
        budget_hint: Optional[float] = None,
        user_styles: Optional[List[str]] = None,
        user_colors: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        prompt_lower = prompt.lower().strip()

        # 1. Detect Occasion & Formality
        occasion = occasion_hint or "Smart Casual"
        formality = "smart_casual"

        if any(w in prompt_lower for w in ["wedding", "marriage", "gala", "black tie", "black-tie", "tuxedo", "formal", "reception", "ball", "suit"]):
            occasion = "Formal & Wedding"
            formality = "formal"
            if any(w in prompt_lower for w in ["black tie", "black-tie", "tuxedo", "gala"]):
                formality = "black_tie"
        elif any(w in prompt_lower for w in ["work", "office", "business", "meeting", "boardroom", "presentation", "interview", "corporate", "executive"]):
            occasion = "Work & Business"
            formality = "business_formal"
        elif any(w in prompt_lower for w in ["party", "dinner", "cocktail", "date", "night out", "gallery", "opening", "evening"]):
            occasion = "Evening & Party"
            formality = "cocktail"
        elif any(w in prompt_lower for w in ["weekend", "brunch", "casual", "relaxed", "vacation", "resort", "travel", "summer", "linen"]):
            occasion = "Casual Weekend"
            formality = "casual"

        # 2. Detect Budget Mentions - Decimal exact
        budget_match = re.search(r'(?:under|below|budget(?:\s*of)?|\$)\s*(\d+)', prompt_lower)
        if budget_match:
            parsed_budget = to_decimal(budget_match.group(1))
        elif budget_hint is not None:
            parsed_budget = to_decimal(budget_hint)
        else:
            parsed_budget = Decimal("450.00")
        # A budget is a HARD constraint only when the user actually stated one
        # (in text or via the explicit occasion/budget hint). A profile default
        # (e.g. the 450.0 fallback) is NOT a hard constraint — the caller passes
        # budget_hint=None when no explicit/user-stated budget exists.
        budget_explicit = bool(budget_match) or (budget_hint is not None)

        # 3. Detect Keywords
        requested_dress = any(w in prompt_lower for w in ["dress", "gown", "maxi", "slip dress", "column dress"])
        requested_suit = any(w in prompt_lower for w in ["suit", "blazer", "tuxedo", "double-breasted", "tailored"])
        requested_tie = any(w in prompt_lower for w in ["tie", "necktie", "bow tie"])
        requested_linen = "linen" in prompt_lower
        requested_silk = "silk" in prompt_lower
        requested_navy = "navy" in prompt_lower
        requested_black = "black" in prompt_lower
        requested_white = "white" in prompt_lower or "ivory" in prompt_lower
        requested_monochrome = any(w in prompt_lower for w in ["monochrome", "monochromatic", "tonal", "all navy", "all black"])

        aesthetic = "Quiet Luxury"
        if user_styles and len(user_styles) > 0:
            aesthetic = user_styles[0]
        if "minimalist" in prompt_lower or "minimal" in prompt_lower:
            aesthetic = "Modern Minimalist"
        elif "old money" in prompt_lower or "classic" in prompt_lower:
            aesthetic = "Old Money / Tailored Classic"
        elif "modern" in prompt_lower or "contemporary" in prompt_lower:
            aesthetic = "Contemporary Tailored"

        # Ambiguity detection (GROUP 2 fix, BRD 21/E2E-12): a meaningful request
        # carries at least one real signal — an occasion keyword, a budget, a
        # style/color/garment request, or an explicit occasion hint. Gibberish or
        # empty prompts must be flagged so the service can ask for clarification
        # instead of returning confident fabricated recommendations.
        has_signal = any([
            occasion_hint,
            budget_match,
            occasion != "Smart Casual",  # an occasion keyword matched
            requested_dress, requested_suit, requested_tie, requested_linen,
            requested_silk, requested_navy, requested_black, requested_white,
            requested_monochrome,
            any(w in prompt_lower for w in ["minimalist", "minimal", "old money", "classic", "modern", "contemporary"]),
            # At least one SIGNAL-BEARING styling token present (occasion /
            # garment / color / material / formality). Pure filler words like
            # "nice"/"stylish"/"something" are excluded -> they stay ambiguous.
            any(t in _SIGNAL_VOCAB for t in re.findall(r"[a-z]{2,}", prompt_lower)),
        ])
        intent_out = {
            "occasion": occasion,
            "formality": formality,
            "detected_budget": parsed_budget,
            "aesthetic": aesthetic,
            "requested_dress": requested_dress,
            "requested_suit": requested_suit,
            "requested_tie": requested_tie,
            "requested_linen": requested_linen,
            "requested_silk": requested_silk,
            "requested_navy": requested_navy,
            "requested_black": requested_black,
            "requested_white": requested_white,
            "requested_monochrome": requested_monochrome,
            "budget_explicit": budget_explicit,
            "is_ambiguous": not has_signal,
            "raw_prompt": prompt,
        }
        return intent_out

    def compose_outfits(
        self,
        available_products: List[Any],
        intent: Dict[str, Any],
        user_profile: Optional[Any] = None,
        max_outfits: int = 2
    ) -> List[Dict[str, Any]]:
        if not available_products:
            return []

        occasion = intent.get("occasion", "Smart Casual")
        formality = intent.get("formality", "smart_casual")
        budget_limit = intent.get("detected_budget", 450.0)
        aesthetic = intent.get("aesthetic", "Quiet Luxury")

        # Classify products into slot buckets
        slot_map: Dict[SlotType, List[Any]] = {st: [] for st in SlotType}
        for prod in available_products:
            st, f_num = classify_product_slot(prod)
            prod._detected_slot = st
            prod._formality_num = int(f_num)
            slot_map[st].append(prod)

        def score_item_for_context(p: Any, slot_expected: SlotType) -> float:
            score = 60.0
            p_style = getattr(p, "style_tags", "[]") or "[]"
            p_occ = getattr(p, "occasion_tags", "[]") or "[]"
            p_color = (getattr(p, "color_family", "") or "").lower()
            p_title = getattr(p, "title", "").lower()

            if formality in ["formal", "black_tie"]:
                if any(tag in p_style for tag in ["formal", "black_tie", "quiet_luxury", "tailored"]):
                    score += 30
                if any(occ in p_occ for occ in ["wedding", "formal", "gala"]):
                    score += 25
                if "sneaker" in p_title or "denim" in p_title or "t-shirt" in p_title:
                    score -= 100
            elif formality == "business_formal":
                if any(tag in p_style for tag in ["smart_casual", "quiet_luxury", "tailored"]):
                    score += 25
                if any(occ in p_occ for occ in ["work", "business"]):
                    score += 25
            elif formality == "cocktail":
                if any(tag in p_style for tag in ["evening", "quiet_luxury", "formal"]):
                    score += 25
                if any(occ in p_occ for occ in ["party", "dinner", "wedding"]):
                    score += 25
            elif formality == "casual":
                if any(tag in p_style for tag in ["smart_casual", "minimalist", "casual", "relaxed_elegance"]):
                    score += 25

            if intent.get("requested_navy") and "navy" in p_color:
                score += 20
            if intent.get("requested_black") and ("black" in p_color or "midnight" in p_color):
                score += 20
            if intent.get("requested_linen") and "linen" in p_title:
                score += 25
            if intent.get("requested_silk") and "silk" in p_title:
                score += 25

            return score

        for st in slot_map:
            slot_map[st].sort(key=lambda p: score_item_for_context(p, st), reverse=True)

        is_dress_intent = intent.get("requested_dress", False) or (formality in ["cocktail", "formal"] and len(slot_map[SlotType.DRESS]) > 0 and not intent.get("requested_suit", False))

        outfits = []
        used_product_ids = set()

        # =========================================================================
        # --- LOOK 1: PRIMARY CURATED ENSEMBLE ---
        # =========================================================================
        look1_items = []
        if is_dress_intent and slot_map[SlotType.DRESS]:
            dress = slot_map[SlotType.DRESS][0]
            used_product_ids.add(dress.id)
            look1_items.append(self._to_item_dict(dress, "dress", SlotType.DRESS, 0, "Anchor Statement Garment"))

            # Footwear (Heeled sandals / dress pumps)
            shoes = slot_map[SlotType.SEMI_FORMAL_SHOES][0] if slot_map[SlotType.SEMI_FORMAL_SHOES] else (slot_map[SlotType.FORMAL_SHOES][0] if slot_map[SlotType.FORMAL_SHOES] else None)
            if shoes:
                used_product_ids.add(shoes.id)
                look1_items.append(self._to_item_dict(shoes, "footwear", SlotType.SEMI_FORMAL_SHOES, 1, "Evening Footwear"))

            # Accessory (Clutch / Jewelry / Pocket Square)
            acc = slot_map[SlotType.BAG][0] if slot_map[SlotType.BAG] else (slot_map[SlotType.POCKET_SQUARE][0] if slot_map[SlotType.POCKET_SQUARE] else (slot_map[SlotType.WATCH][0] if slot_map[SlotType.WATCH] else None))
            if acc:
                used_product_ids.add(acc.id)
                look1_items.append(self._to_item_dict(acc, "accessory", SlotType.BAG, 2, "Bespoke Evening Hardware"))

            title1 = f"The {occasion} Silk Column Silhouette"
            desc1 = f"A statuesque fluid silhouette anchored by {dress.brand.brand_name} {dress.title}, paired with sculptural metallic footwear."

        else:
            # Separates / Tailored Suit Route
            # 1. Outerwear / Blazer
            if formality in ["formal", "black_tie"]:
                outer_cands = slot_map[SlotType.FORMAL_OUTER]
            elif formality in ["business_formal"]:
                outer_cands = slot_map[SlotType.FORMAL_OUTER] + slot_map[SlotType.SEMI_FORMAL_OUTER]
            else:
                outer_cands = slot_map[SlotType.SEMI_FORMAL_OUTER] + slot_map[SlotType.FORMAL_OUTER]

            outer = outer_cands[0] if outer_cands else None
            if outer:
                used_product_ids.add(outer.id)
                look1_items.append(self._to_item_dict(outer, "outerwear", outer._detected_slot, 0, "Tailored Outerwear Anchor"))

            # 2. Formal / Coordinated Top
            if formality in ["formal", "black_tie", "business_formal"]:
                top_cands = slot_map[SlotType.FORMAL_SHIRT]
            elif formality == "casual":
                top_cands = slot_map[SlotType.CASUAL_SHIRT] + slot_map[SlotType.KNIT_LAYER] + slot_map[SlotType.FORMAL_SHIRT]
            else:
                top_cands = slot_map[SlotType.FORMAL_SHIRT] + slot_map[SlotType.CASUAL_SHIRT]

            top = top_cands[0] if top_cands else (available_products[0] if available_products else None)
            if top:
                used_product_ids.add(top.id)
                look1_items.append(self._to_item_dict(top, "top", top._detected_slot, 1, "Core Layer / Shirt"))

            # 3. Bottoms / Trousers
            if outer and formality in ["formal", "black_tie"]:
                # Match color with jacket
                outer_color = getattr(outer, "color_family", "").lower()
                all_formal_bottoms = slot_map[SlotType.FORMAL_BOTTOM] + slot_map[SlotType.SEMI_FORMAL_BOTTOM]
                matching_bottoms = [b for b in all_formal_bottoms if b.color_family.lower() in outer_color or outer_color in b.color_family.lower()]
                bottom = matching_bottoms[0] if matching_bottoms else (all_formal_bottoms[0] if all_formal_bottoms else None)
            elif formality == "casual":
                bottom_cands = slot_map[SlotType.CASUAL_BOTTOM] + slot_map[SlotType.SEMI_FORMAL_BOTTOM]
                bottom = bottom_cands[0] if bottom_cands else None
            else:
                bottom_cands = slot_map[SlotType.SEMI_FORMAL_BOTTOM] + slot_map[SlotType.FORMAL_BOTTOM]
                bottom = bottom_cands[0] if bottom_cands else None

            if bottom:
                used_product_ids.add(bottom.id)
                look1_items.append(self._to_item_dict(bottom, "bottom", bottom._detected_slot, 2, "Structured Lower Silhouette"))

            # 4. Footwear
            if formality in ["formal", "black_tie"]:
                shoe = slot_map[SlotType.FORMAL_SHOES][0] if slot_map[SlotType.FORMAL_SHOES] else (slot_map[SlotType.SEMI_FORMAL_SHOES][0] if slot_map[SlotType.SEMI_FORMAL_SHOES] else None)
            elif formality == "casual":
                shoe = slot_map[SlotType.CASUAL_SHOES][0] if slot_map[SlotType.CASUAL_SHOES] else (slot_map[SlotType.SEMI_FORMAL_SHOES][0] if slot_map[SlotType.SEMI_FORMAL_SHOES] else None)
            else:
                shoe = slot_map[SlotType.SEMI_FORMAL_SHOES][0] if slot_map[SlotType.SEMI_FORMAL_SHOES] else (slot_map[SlotType.FORMAL_SHOES][0] if slot_map[SlotType.FORMAL_SHOES] else None)

            if shoe:
                used_product_ids.add(shoe.id)
                look1_items.append(self._to_item_dict(shoe, "footwear", shoe._detected_slot, 3, "Polished Footwear Foundation"))

            # 5. Accessory (Tie / Pocket Square / Belt / Watch)
            if formality in ["formal", "black_tie", "wedding"]:
                acc = slot_map[SlotType.TIE][0] if slot_map[SlotType.TIE] else (slot_map[SlotType.POCKET_SQUARE][0] if slot_map[SlotType.POCKET_SQUARE] else None)
            else:
                acc = slot_map[SlotType.WATCH][0] if slot_map[SlotType.WATCH] else (slot_map[SlotType.BELT][0] if slot_map[SlotType.BELT] else None)

            if acc:
                used_product_ids.add(acc.id)
                look1_items.append(self._to_item_dict(acc, "accessory", acc._detected_slot, 4, "Refined Accenting Hardware"))

            title1 = f"The Essential {occasion} Tailored Look"
            desc1 = f"A cohesive multi-brand ensemble combining structured {outer.brand.brand_name if outer else 'tailoring'} with pristine {top.brand.brand_name if top else 'cotton'} and Goodyear-welted footwear."

        look1_items, budget1 = self._enforce_budget(look1_items, slot_map, used_product_ids, budget_limit, intent)
        total1_dec = money_sum([to_decimal(i["price"]) for i in look1_items])
        total1 = to_float(total1_dec)
        eval1 = self.rules_engine.evaluate_outfit(look1_items, intent)

        palette1 = [i["color_hex"] for i in look1_items]
        if len(palette1) < 3:
            palette1.extend(["#FAF9F6", "#C5A059"])

        outfits.append({
            "id": 101,
            "title": title1,
            "description": desc1,
            "occasion": occasion,
            "total_price": total1,
            "compatibility_score": eval1["composite_score"],
            "color_palette": palette1[:4],
            "style_tags": [aesthetic, "Precision Coordinated", eval1["completeness_label"]],
            "is_saved": False,
            "is_system_curated": True,
            "is_complete": eval1["is_complete"],
            "completeness_status": eval1["completeness_status"],
            "completeness_label": eval1["completeness_label"],
            "missing_slots": eval1["missing_slots"],
            "color_harmony_score": eval1["color_harmony_score"],
            "formality_score": 95,
            "budget_limit": budget1["budget_limit"],
            "within_budget": budget1["within_budget"],
            "budget_note": budget1["budget_note"],
            "items": look1_items,
            "created_at": look1_items[0]["created_at"] if look1_items else "2026-08-18T00:00:00Z"
        })

        if max_outfits <= 1:
            return outfits

        # =========================================================================
        # --- LOOK 2: ALTERNATIVE COORDINATED LOOK (DIVERSE & NON-OVERLAPPING) ---
        # =========================================================================
        look2_items = []
        alt_dresses = [p for p in slot_map[SlotType.DRESS] if p.id not in used_product_ids]
        alt_outers = [p for p in (slot_map[SlotType.FORMAL_OUTER] + slot_map[SlotType.SEMI_FORMAL_OUTER] + slot_map[SlotType.CASUAL_OUTER]) if p.id not in used_product_ids]
        alt_tops = [p for p in (slot_map[SlotType.FORMAL_SHIRT] + slot_map[SlotType.CASUAL_SHIRT] + slot_map[SlotType.KNIT_LAYER] + slot_map[SlotType.T_SHIRT]) if p.id not in used_product_ids]
        alt_bottoms = [p for p in (slot_map[SlotType.FORMAL_BOTTOM] + slot_map[SlotType.SEMI_FORMAL_BOTTOM] + slot_map[SlotType.CASUAL_BOTTOM]) if p.id not in used_product_ids]
        alt_shoes = [p for p in (slot_map[SlotType.FORMAL_SHOES] + slot_map[SlotType.SEMI_FORMAL_SHOES] + slot_map[SlotType.CASUAL_SHOES]) if p.id not in used_product_ids]
        alt_accs = [p for p in (slot_map[SlotType.TIE] + slot_map[SlotType.POCKET_SQUARE] + slot_map[SlotType.BELT] + slot_map[SlotType.BAG] + slot_map[SlotType.WATCH]) if p.id not in used_product_ids]

        if not is_dress_intent and alt_dresses and formality in ["formal", "wedding", "cocktail"]:
            alt_dress = alt_dresses[0]
            look2_items.append(self._to_item_dict(alt_dress, "dress", SlotType.DRESS, 0, "Flowing Evening Drape"))

            alt_shoe = alt_shoes[0] if alt_shoes else (slot_map[SlotType.SEMI_FORMAL_SHOES][0] if slot_map[SlotType.SEMI_FORMAL_SHOES] else None)
            if alt_shoe:
                look2_items.append(self._to_item_dict(alt_shoe, "footwear", alt_shoe._detected_slot, 1, "Sculpted Evening Footwear"))

            alt_acc = alt_accs[0] if alt_accs else (slot_map[SlotType.BAG][0] if slot_map[SlotType.BAG] else None)
            if alt_acc:
                look2_items.append(self._to_item_dict(alt_acc, "accessory", alt_acc._detected_slot, 2, "Metallic Accent Piece"))

            title2 = f"The Contemporary {occasion} Drape"
            desc2 = f"A refined evening alternative centered around {alt_dress.brand.brand_name} {alt_dress.title}."
        else:
            alt_outer = alt_outers[0] if alt_outers else None
            if alt_outer:
                look2_items.append(self._to_item_dict(alt_outer, "outerwear", alt_outer._detected_slot, 0, "Contemporary Outer Layer"))

            alt_top = alt_tops[0] if alt_tops else (slot_map[SlotType.FORMAL_SHIRT][0] if slot_map[SlotType.FORMAL_SHIRT] else None)
            if alt_top:
                look2_items.append(self._to_item_dict(alt_top, "top", alt_top._detected_slot, 1, "Tonal Underlayer"))

            alt_bottom = alt_bottoms[0] if alt_bottoms else (slot_map[SlotType.SEMI_FORMAL_BOTTOM][0] if slot_map[SlotType.SEMI_FORMAL_BOTTOM] else None)
            if alt_bottom:
                look2_items.append(self._to_item_dict(alt_bottom, "bottom", alt_bottom._detected_slot, 2, "Tonal Lower Silhouette"))

            alt_shoe = alt_shoes[0] if alt_shoes else (slot_map[SlotType.SEMI_FORMAL_SHOES][0] if slot_map[SlotType.SEMI_FORMAL_SHOES] else None)
            if alt_shoe:
                look2_items.append(self._to_item_dict(alt_shoe, "footwear", alt_shoe._detected_slot, 3, "Modern Footwear"))

            alt_acc = alt_accs[0] if alt_accs else (slot_map[SlotType.POCKET_SQUARE][0] if slot_map[SlotType.POCKET_SQUARE] else None)
            if alt_acc:
                look2_items.append(self._to_item_dict(alt_acc, "accessory", alt_acc._detected_slot, 4, "Signature Accenting Piece"))

            title2 = f"The Modern Tonal {occasion} Look"
            desc2 = f"A modern textured silhouette featuring {alt_top.brand.brand_name if alt_top else 'contemporary'} layers and tonal balance."

        if look2_items:
            look2_items, budget2 = self._enforce_budget(look2_items, slot_map, used_product_ids, budget_limit, intent)
            total2_dec = money_sum([to_decimal(i["price"]) for i in look2_items])
            total2 = to_float(total2_dec)
            eval2 = self.rules_engine.evaluate_outfit(look2_items, intent)

            palette2 = [i["color_hex"] for i in look2_items]
            if len(palette2) < 3:
                palette2.extend(["#FAF9F6", "#C5A059"])

            outfits.append({
                "id": 102,
                "title": title2,
                "description": desc2,
                "occasion": occasion,
                "total_price": total2,
                "compatibility_score": eval2["composite_score"],
                "color_palette": palette2[:4],
                "style_tags": ["Modern Silhouette", "Tonal Harmony", eval2["completeness_label"]],
                "is_saved": False,
                "is_system_curated": True,
                "is_complete": eval2["is_complete"],
                "completeness_status": eval2["completeness_status"],
                "completeness_label": eval2["completeness_label"],
                "missing_slots": eval2["missing_slots"],
                "color_harmony_score": eval2["color_harmony_score"],
                "formality_score": 92,
                "budget_limit": budget2["budget_limit"],
                "within_budget": budget2["within_budget"],
                "budget_note": budget2["budget_note"],
                "items": look2_items,
                "created_at": look2_items[0]["created_at"] if look2_items else "2026-08-18T00:00:00Z"
            })

        return outfits

    def _candidate_pool(self, slot_map: Dict[SlotType, List[Any]], position: str) -> List[Any]:
        """Ordered candidate pool for a coarse canvas position, cheapest last is
        NOT assumed — callers sort by price when substituting."""
        pools = {
            "dress": [SlotType.DRESS, SlotType.JUMPSUIT],
            "outerwear": [SlotType.FORMAL_OUTER, SlotType.SEMI_FORMAL_OUTER, SlotType.CASUAL_OUTER],
            "top": [SlotType.FORMAL_SHIRT, SlotType.CASUAL_SHIRT, SlotType.KNIT_LAYER, SlotType.T_SHIRT],
            "bottom": [SlotType.FORMAL_BOTTOM, SlotType.SEMI_FORMAL_BOTTOM, SlotType.CASUAL_BOTTOM],
            "footwear": [SlotType.FORMAL_SHOES, SlotType.SEMI_FORMAL_SHOES, SlotType.CASUAL_SHOES, SlotType.BOOTS],
            "accessory": [SlotType.TIE, SlotType.POCKET_SQUARE, SlotType.BELT, SlotType.BAG, SlotType.WATCH],
        }
        out: List[Any] = []
        for st in pools.get(position, []):
            out.extend(slot_map.get(st, []))
        return out

    def _enforce_budget(
        self,
        items: List[Dict[str, Any]],
        slot_map: Dict[SlotType, List[Any]],
        used_product_ids: set,
        budget_limit: Any,
        intent: Dict[str, Any],
    ):
        """Deterministic budget enforcement — Decimal exact."""
        budget_dec = to_decimal(budget_limit) if budget_limit is not None else Decimal("450.00")

        if not items or not intent.get("budget_explicit"):
            for it in items:
                it["budget_status"] = "within_budget"
            return items, {"budget_limit": None, "within_budget": True, "budget_note": None}

        def total_dec(lst):
            return money_sum([to_decimal(i["price"]) for i in lst])

        def cheapest_per_position(positions):
            out = {}
            for pos in positions:
                cands = self._candidate_pool(slot_map, pos)
                if not cands:
                    return None
                cands = sorted(cands, key=lambda p: (
                    to_decimal(p.base_price),
                    0 if (getattr(p, "skus", None) and any(s.is_in_stock and s.stock_level > 0 for s in p.skus)) else 1,
                ))
                out[pos] = cands[0]
            return out

        def build_min_look():
            sep = cheapest_per_position(["top", "bottom", "footwear"])
            dres = cheapest_per_position(["dress", "footwear"])
            options = []
            if sep:
                sep_cost = money_sum([to_decimal(p.base_price) for p in sep.values()])
                options.append(("separates", sep, sep_cost))
            if dres:
                dres_cost = money_sum([to_decimal(p.base_price) for p in dres.values()])
                options.append(("onepiece", dres, dres_cost))
            if not options:
                return None, None
            kind, best, cost = min(options, key=lambda o: o[2])
            return best, cost

        min_core, min_core_cost = build_min_look()

        if total_dec(items) > budget_dec and min_core is not None:
            rebuilt = []
            for idx, (pos, prod) in enumerate(min_core.items()):
                rebuilt.append(self._to_item_dict(prod, pos, prod._detected_slot, idx, "Budget-Conscious Core"))
                used_product_ids.add(prod.id)
            if min_core_cost is not None and min_core_cost <= budget_dec:
                ess = set(min_core.keys())
                extras = sorted(
                    (i for i in items if i["position"] not in ess),
                    key=lambda i: to_decimal(i["price"]),
                )
                for ex in extras:
                    if total_dec(rebuilt) + to_decimal(ex["price"]) <= budget_dec:
                        rebuilt.append(ex)
            items = rebuilt

        final_total_dec = total_dec(items)
        within = final_total_dec <= budget_dec
        for it in items:
            it["budget_status"] = "within_budget" if within else "over_budget"
        if within:
            note = f"Outfit total ${to_float(final_total_dec):.2f} is within your ${to_float(budget_dec):.2f} budget."
        else:
            floor = min_core_cost if min_core_cost is not None else final_total_dec
            note = (f"Could not reach ${to_float(budget_dec):.2f} with the current catalog; "
                    f"the minimum complete look available is ${to_float(floor):.2f}.")
        return items, {"budget_limit": to_float(budget_dec), "within_budget": within, "budget_note": note}

    def _to_item_dict(self, product: Any, position: str, slot_type: SlotType, sort_order: int, role: str) -> Dict[str, Any]:
        first_sku = product.skus[0] if hasattr(product, "skus") and product.skus else None
        created_at_str = product.created_at.isoformat() if hasattr(product, "created_at") and hasattr(product.created_at, "isoformat") else "2026-08-18T00:00:00Z"

        return {
            "id": product.id * 10 + sort_order,
            "product_id": product.id,
            "product_title": product.title,
            "brand_name": product.brand.brand_name if hasattr(product, "brand") and product.brand else "CONFIT Partner",
            "category_name": product.category.name if hasattr(product, "category") and product.category else "Apparel",
            "price": to_float(product.base_price),
            "image_url": product.thumbnail_url,
            "color_hex": product.dominant_hex or "#1B1F3B",
            "color_family": getattr(product, "color_family", "Neutral"),
            "material": getattr(product, "material", "Fine Fabric"),
            "position": position,
            "slot_type": slot_type.value,
            "formality_num": getattr(product, "_formality_num", 3),
            "occasion_tags": getattr(product, "occasion_tags", "[]"),
            "role_in_outfit": role,
            "sku_id": first_sku.id if first_sku else None,
            "selected_size": first_sku.size if first_sku else "M",
            "created_at": created_at_str
        }
