from typing import List, Dict, Any, Optional


class ColorHarmonyEngine:
    """Color harmony evaluation and palette scoring subsystem.

    Honest scoring contract (GROUP 2 fix):
      * Scores are DERIVED from the fraction of color pairs that harmonize and
        the detected harmony relationship. There is NO artificial floor/ceiling
        designed to make every result look good.
      * A clashing or incoherent palette MUST score meaningfully lower than a
        coherent one. Empty input scores 0.
      * The numeric score is deterministic and testable: identical input always
        yields the identical score.
    """

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
        "#2D4A3E": "Sage Green",
    }

    # Canonical color-family keywords treated as neutrals (pair with anything).
    NEUTRAL_FAMILIES = {
        "black", "midnight", "obsidian", "ebony", "white", "optic", "ivory",
        "alabaster", "cream", "grey", "gray", "charcoal", "beige", "sand",
        "tan", "camel", "brown", "espresso", "navy", "denim",
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
        "sage": ["cream", "beige", "navy", "white", "gold", "camel", "charcoal"],
    }

    @classmethod
    def _is_neutral(cls, color: str) -> bool:
        return any(n in color for n in cls.NEUTRAL_FAMILIES)

    @classmethod
    def _pairs_harmonize(cls, c1: str, c2: str) -> Optional[bool]:
        """Return True/False for a known relationship, None when unknown.

        Same-family (monochrome) and any neutral pairing harmonize. A pair of
        two distinct non-neutral colors that is NOT in the harmony matrix is a
        genuine clash (False). Unknown is reserved for empty color metadata.
        """
        if not c1 or not c2:
            return None
        # Monochromatic: same dominant family word.
        toks1 = set(c1.split())
        toks2 = set(c2.split())
        if toks1 & toks2:
            return True
        # Neutral pieces harmonize with everything.
        if cls._is_neutral(c1) or cls._is_neutral(c2):
            return True
        # Explicit harmony matrix (both directions).
        for key, targets in cls.HARMONY_PAIRS.items():
            if key in c1 and any(t in c2 for t in targets):
                return True
            if key in c2 and any(t in c1 for t in targets):
                return True
        # Two non-neutral, non-matching colors with no known harmony = clash.
        return False

    @classmethod
    def evaluate_palette(cls, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Evaluate color harmony and return an honest, derived score (0-100)."""
        if not items:
            return {
                "color_harmony_score": 0,
                "harmony_type": "None",
                "verdict": "No items provided",
                "leather_consistent": True,
            }

        colors = [(it.get("color_family") or "").lower() for it in items]

        # Single item: a lone piece is inherently coherent (no clash possible),
        # but it is not a "palette" — score it as neutrally good, not maximal.
        if len(items) == 1:
            return {
                "color_harmony_score": 75,
                "harmony_type": "Single Piece",
                "verdict": "Single piece selected; no palette interactions to harmonize.",
                "leather_consistent": True,
            }

        matched = 0
        clashed = 0
        unknown = 0
        total_checks = 0
        for i, c1 in enumerate(colors):
            for j in range(i + 1, len(colors)):
                total_checks += 1
                res = cls._pairs_harmonize(c1, colors[j])
                if res is True:
                    matched += 1
                elif res is False:
                    clashed += 1
                else:
                    unknown += 1

        evaluated = matched + clashed
        match_ratio = (matched / evaluated) if evaluated > 0 else 0.5

        # Leather tone consistency (shoe/belt/watch strap metals & leathers).
        leather_items = [
            it for it in items
            if it.get("position") in ["footwear", "accessory"]
            and any(w in (it.get("product_title", "").lower()) for w in ["shoe", "oxford", "loafer", "derby", "belt", "watch", "sandal"])
        ]
        leather_colors = [it.get("color_family", "").lower() for it in leather_items]
        leather_consistent = not (
            any("black" in lc or "obsidian" in lc for lc in leather_colors)
            and any("brown" in lc or "tan" in lc for lc in leather_colors)
        )

        # Honest derived score: harmony fraction drives the score; clashes and
        # leather mismatches apply real penalties. No floor that rescues clashes.
        score = match_ratio * 100.0
        if clashed > 0:
            score -= clashed * 12.0
        if not leather_consistent:
            score -= 15.0
        score = int(round(min(100.0, max(0.0, score))))

        # Classify the harmony relationship.
        families = [c for c in colors if c]
        distinct = len({f for f in families})
        if clashed > 0 and match_ratio < 0.6:
            harmony_type = "Clashing / Disconnected"
            verdict = f"{clashed} color pairing(s) clash; palette lacks cohesion."
        elif distinct <= 1 or match_ratio >= 0.85:
            harmony_type = "Tonal Monochromatic" if distinct <= 2 else "Complementary Balanced Contrast"
            verdict = "Cohesive palette: tones harmonize with balanced contrast and depth."
        elif match_ratio >= 0.6:
            harmony_type = "Analogous Harmonized"
            verdict = "Mostly harmonious palette with acceptable color relationships."
        else:
            harmony_type = "Mixed"
            verdict = "Palette shows some discordant pairings that weaken cohesion."

        return {
            "color_harmony_score": score,
            "harmony_type": harmony_type,
            "verdict": verdict,
            "leather_consistent": leather_consistent,
        }
