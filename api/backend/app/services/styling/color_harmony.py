from typing import List, Dict, Any, Tuple


class ColorHarmonyEngine:
    """Color harmony evaluation and palette scoring subsystem."""

    NEUTRAL_HEXES = {
        "#000000": "Black",
        "#0B0C10": "Midnight Black",
        "#111111": "Ebony Black",
        "#FFFFFF": "Optic White",
        "#FAF9F6": "Alabaster White",
        "#F5F2EB": "Ivory Cream",
        "#1B1F3B": "Navy Blue",
        "#373D43": "Charcoal Grey",
        "#D8C7B5": "Beige Sand",
        "#4A3525": "Espresso Brown",
        "#B8860B": "Camel Tan",
        "#C5A059": "Champagne Gold",
        "#1E4D3B": "Emerald Green",
        "#2D4A3E": "Sage Green"
    }

    HARMONY_PAIRS = {
        "navy": ["beige", "white", "tan", "gold", "olive", "burgundy", "light blue", "grey", "emerald", "ivory", "black", "sand", "champagne"],
        "beige": ["navy", "black", "forest green", "terracotta", "white", "brown", "cream", "gold", "sage", "charcoal"],
        "black": ["white", "grey", "beige", "camel", "red", "gold", "olive", "navy", "emerald", "ivory", "champagne", "charcoal"],
        "white": ["navy", "black", "beige", "olive", "denim", "charcoal", "emerald", "gold", "sage", "camel", "champagne"],
        "ivory": ["navy", "black", "gold", "emerald", "charcoal", "camel", "champagne", "sage", "sand"],
        "emerald": ["navy", "white", "ivory", "gold", "black", "charcoal", "beige", "camel"],
        "gold": ["navy", "black", "ivory", "white", "champagne", "emerald", "burgundy", "charcoal"],
        "champagne": ["gold", "black", "navy", "ivory", "white", "emerald", "charcoal"],
        "charcoal": ["white", "ivory", "navy", "black", "camel", "emerald", "gold", "sage"],
        "camel": ["navy", "black", "white", "cream", "forest green", "denim", "charcoal", "ivory"],
        "sage": ["cream", "beige", "navy", "white", "gold", "camel", "charcoal"]
    }

    @classmethod
    def evaluate_palette(cls, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Evaluates color harmony, leather tone alignment, and color balance across items."""
        if not items:
            return {
                "color_harmony_score": 0,
                "harmony_type": "None",
                "verdict": "No items provided",
                "leather_consistent": True
            }

        colors = [(it.get("color_family") or "").lower() for it in items]
        positions = [it.get("position") for it in items]

        # 1. Evaluate general harmony pairs
        pair_matches = 0
        total_checks = 0

        for i, c1 in enumerate(colors):
            for j, c2 in enumerate(colors):
                if i >= j:
                    continue
                total_checks += 1
                matched = False
                for key, targets in cls.HARMONY_PAIRS.items():
                    if key in c1 and any(t in c2 for t in targets):
                        matched = True
                        break
                    elif key in c2 and any(t in c1 for t in targets):
                        matched = True
                        break
                if matched:
                    pair_matches += 1

        match_ratio = (pair_matches / max(1, total_checks)) if total_checks > 0 else 1.0

        # 2. Leather consistency check (Shoe vs Belt vs Watch strap)
        leather_items = [it for it in items if it.get("position") in ["footwear", "accessory"] and any(w in it.get("product_title", "").lower() for w in ["shoe", "oxford", "loafer", "derby", "belt", "watch", "sandal"])]
        leather_consistent = True
        leather_colors = [it.get("color_family", "").lower() for it in leather_items]
        if any("black" in lc for lc in leather_colors) and any("brown" in lc or "tan" in lc for lc in leather_colors):
            leather_consistent = False

        # Compute Score
        base_score = 88.0
        base_score += match_ratio * 8.0
        if leather_consistent:
            base_score += 2.0
        else:
            base_score -= 5.0

        score = int(min(98, max(75, base_score)))

        if match_ratio >= 0.8:
            harmony_type = "Complementary Balanced Contrast"
            verdict = "Exceptional palette synergy: tailored tones harmoniously balance contrast and depth."
        else:
            harmony_type = "Tonal Monochromatic"
            verdict = "Understated tonal cohesion across all selected pieces."

        return {
            "color_harmony_score": score,
            "harmony_type": harmony_type,
            "verdict": verdict,
            "leather_consistent": leather_consistent
        }
