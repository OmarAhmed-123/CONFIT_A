"""Authoritative wardrobe taxonomy + AI-output normalization (Group 4).

One canonical vocabulary for wardrobe categories, colors, patterns, styles and
occasions so that free-form vision-model output (\"Navy Blue\", \"dark navy\",
\"midnight\") collapses onto the same controlled values the rest of the
platform already uses (catalog ``color_family``, the styling slot ontology and
the color-harmony engine). This module is pure/deterministic and unit-tested;
it never calls a model.
"""
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

# ── Wardrobe categories (BRD §4.1) ──────────────────────────────────────────
WARDROBE_CATEGORIES = ["Tops", "Bottoms", "Outerwear", "Footwear", "Accessories", "Dresses"]

_CATEGORY_ALIASES = {
    "tops": "Tops", "top": "Tops", "shirt": "Tops", "t-shirt": "Tops", "tshirt": "Tops",
    "tee": "Tops", "blouse": "Tops", "polo": "Tops", "sweater": "Tops", "knitwear": "Tops",
    "hoodie": "Tops", "sweatshirt": "Tops", "cardigan": "Tops", "camisole": "Tops",
    "bottoms": "Bottoms", "bottom": "Bottoms", "trousers": "Bottoms", "pants": "Bottoms",
    "jeans": "Bottoms", "chinos": "Bottoms", "skirt": "Bottoms", "shorts": "Bottoms",
    "joggers": "Bottoms", "leggings": "Bottoms",
    "outerwear": "Outerwear", "jacket": "Outerwear", "blazer": "Outerwear", "coat": "Outerwear",
    "overcoat": "Outerwear", "trench": "Outerwear", "parka": "Outerwear", "suit jacket": "Outerwear",
    "footwear": "Footwear", "shoes": "Footwear", "shoe": "Footwear", "sneakers": "Footwear",
    "boots": "Footwear", "loafers": "Footwear", "heels": "Footwear", "sandals": "Footwear",
    "oxfords": "Footwear", "derby": "Footwear", "trainers": "Footwear",
    "accessories": "Accessories", "accessory": "Accessories", "belt": "Accessories",
    "tie": "Accessories", "watch": "Accessories", "bag": "Accessories", "hat": "Accessories",
    "scarf": "Accessories", "sunglasses": "Accessories", "jewelry": "Accessories",
    "dresses": "Dresses", "dress": "Dresses", "gown": "Dresses", "jumpsuit": "Dresses",
}

# ── Canonical color families (aligned with ColorHarmonyEngine vocabulary) ───
# Map of canonical name -> alias tokens that normalize to it. Matching is
# substring-based so "Navy Blue" / "dark navy" / "navy" all become "Navy".
COLOR_FAMILIES: Dict[str, List[str]] = {
    "Black": ["black", "midnight", "obsidian", "ebony", "onyx", "charcoal black"],
    "White": ["white", "optic white", "off-white", "off white", "snow"],
    "Ivory": ["ivory", "alabaster", "cream", "ecru", "bone"],
    "Grey": ["grey", "gray", "charcoal", "slate", "heather", "graphite", "ash"],
    "Navy": ["navy", "navy blue", "dark navy", "midnight blue", "ink blue", "marine"],
    "Blue": ["blue", "sky blue", "royal blue", "cobalt", "azure", "light blue", "denim blue", "steel blue"],
    "Beige": ["beige", "sand", "khaki", "taupe", "stone", "oat", "oatmeal", "nude"],
    "Tan": ["tan", "camel", "caramel", "toffee", "cognac"],
    "Brown": ["brown", "espresso", "chocolate", "coffee", "mocha", "chestnut", "walnut"],
    "Green": ["green", "emerald", "forest green", "olive", "sage", "mint", "khaki green", "hunter"],
    "Red": ["red", "crimson", "scarlet", "burgundy", "maroon", "wine", "oxblood", "rust", "terracotta"],
    "Pink": ["pink", "blush", "rose", "fuchsia", "magenta", "salmon", "coral pink"],
    "Purple": ["purple", "violet", "lavender", "lilac", "plum", "mauve", "aubergine"],
    "Yellow": ["yellow", "mustard", "gold", "golden", "champagne", "lemon", "amber"],
    "Orange": ["orange", "burnt orange", "apricot", "peach", "copper"],
    "Silver": ["silver", "metallic", "platinum", "pewter"],
    "Multi": ["multi", "multicolor", "multi-color", "colorful", "rainbow"],
}

# Loose hex palette for the canonical families (used when the model does not
# return a hex, or returns an implausible one).
COLOR_FAMILY_HEX = {
    "Black": "#1B1B1B", "White": "#FFFFFF", "Ivory": "#F5F2EB", "Grey": "#6B7280",
    "Navy": "#1B1F3B", "Blue": "#3B5BA9", "Beige": "#D8C7B5", "Tan": "#B8860B",
    "Brown": "#4A3525", "Green": "#2D4A3E", "Red": "#8C2F39", "Pink": "#D9A7B0",
    "Purple": "#6B5B95", "Yellow": "#C5A059", "Orange": "#C4733B", "Silver": "#C0C0C0",
    "Multi": "#888888",
}

# ── Patterns ────────────────────────────────────────────────────────────────
PATTERNS = ["Solid", "Striped", "Checked", "Plaid", "Floral", "Polka Dot", "Graphic",
            "Houndstooth", "Paisley", "Animal Print", "Camouflage", "Geometric",
            "Color Block", "Embroidered", "Textured", "Denim Wash"]

_PATTERN_ALIASES = {
    "solid": "Solid", "plain": "Solid", "none": "Solid",
    "stripe": "Striped", "striped": "Striped", "pinstripe": "Striped",
    "check": "Checked", "checked": "Checked", "checkered": "Checked", "gingham": "Checked",
    "plaid": "Plaid", "tartan": "Plaid", "flannel check": "Plaid",
    "floral": "Floral", "flower": "Floral", "botanical": "Floral",
    "polka": "Polka Dot", "polka dot": "Polka Dot", "dotted": "Polka Dot",
    "graphic": "Graphic", "logo": "Graphic", "print graphic": "Graphic",
    "houndstooth": "Houndstooth", "hound's tooth": "Houndstooth",
    "paisley": "Paisley",
    "animal": "Animal Print", "leopard": "Animal Print", "zebra": "Animal Print", "snake": "Animal Print",
    "camouflage": "Camouflage", "camo": "Camouflage",
    "geometric": "Geometric", "abstract": "Geometric",
    "color block": "Color Block", "colour block": "Color Block", "two-tone": "Color Block",
    "embroidered": "Embroidered", "embroidery": "Embroidered",
    "textured": "Textured", "ribbed": "Textured", "quilted": "Textured", "cable knit": "Textured",
    "denim wash": "Denim Wash", "washed": "Denim Wash", "acid wash": "Denim Wash",
}

# ── Occasions (aligned with styling FormalityLevel ladder) ──────────────────
OCCASIONS = ["Casual", "Smart Casual", "Work & Business", "Business Formal",
             "Cocktail", "Formal", "Black Tie", "Active", "Lounge", "Evening"]

_OCCASION_ALIASES = {
    "casual": "Casual", "everyday": "Casual", "weekend": "Casual",
    "smart casual": "Smart Casual", "smart-casual": "Smart Casual", "smart casual dinner": "Smart Casual",
    "work": "Work & Business", "business": "Work & Business", "office": "Work & Business",
    "work & business": "Work & Business", "business casual": "Work & Business",
    "business formal": "Business Formal", "boardroom": "Business Formal",
    "cocktail": "Cocktail", "party": "Cocktail", "date night": "Cocktail",
    "formal": "Formal", "gala": "Formal", "wedding": "Formal",
    "black tie": "Black Tie", "black-tie": "Black Tie", "white tie": "Black Tie",
    "active": "Active", "gym": "Active", "sport": "Active", "athleisure": "Active", "workout": "Active",
    "lounge": "Lounge", "loungewear": "Lounge", "home": "Lounge",
    "evening": "Evening", "dinner": "Evening", "night out": "Evening",
}

# ── Seasonality (BRD: "Seasonal" item state support) ───────────────────────
SEASONS = ["All-Season", "Spring", "Summer", "Autumn", "Winter"]

_SEASON_ALIASES = {
    "all-season": "All-Season", "all season": "All-Season", "year-round": "All-Season",
    "spring": "Spring", "summer": "Summer", "autumn": "Autumn", "fall": "Autumn",
    "winter": "Winter",
}

# Wear-frequency states (BRD 4.1: Favorite / Rarely Worn / Seasonal)
WEAR_FREQUENCIES = ["favorite", "regular", "rarely_worn", "seasonal"]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _closest(value: str, candidates: List[str], cutoff: float = 0.72) -> Optional[str]:
    """Fuzzy-match a free-form value against a canonical list."""
    v = _norm(value)
    if not v:
        return None
    best, best_score = None, 0.0
    for cand in candidates:
        score = SequenceMatcher(None, v, _norm(cand)).ratio()
        if score > best_score:
            best, best_score = cand, score
    return best if best_score >= cutoff else None


def normalize_category(raw: Optional[str], subcategory_hint: Optional[str] = None) -> str:
    """Collapse model output onto the controlled wardrobe category list."""
    for text in (raw, subcategory_hint):
        v = _norm(text or "")
        if not v:
            continue
        for alias, canonical in _CATEGORY_ALIASES.items():
            if alias in v:
                return canonical
        match = _closest(v, WARDROBE_CATEGORIES)
        if match:
            return match
    return "Tops"  # safest default bucket for an unrecognized garment


def normalize_color(raw: Optional[str]) -> str:
    """Normalize 'Navy Blue' / 'dark navy' / 'midnight' to one family."""
    v = _norm(raw or "")
    if not v:
        return "Black"
    # Longest alias first so 'navy blue' wins over 'blue'
    aliases = sorted(
        ((alias, fam) for fam, toks in COLOR_FAMILIES.items() for alias in toks),
        key=lambda t: len(t[0]),
        reverse=True,
    )
    for alias, fam in aliases:
        if alias in v:
            return fam
    match = _closest(v, list(COLOR_FAMILIES.keys()))
    return match or "Black"


def color_hex_for_family(family: str, model_hex: Optional[str] = None) -> str:
    """Prefer a plausible model-returned hex; fall back to the family default."""
    if model_hex and re.fullmatch(r"#[0-9a-fA-F]{6}", model_hex.strip()):
        return model_hex.strip().upper()
    return COLOR_FAMILY_HEX.get(family, "#1B1B1B")


def normalize_pattern(raw: Optional[str]) -> str:
    v = _norm(raw or "")
    if not v:
        return "Solid"
    for alias, canonical in sorted(_PATTERN_ALIASES.items(), key=lambda t: len(t[0]), reverse=True):
        if alias in v:
            return canonical
    match = _closest(v, PATTERNS)
    return match or "Solid"


def normalize_occasions(raw_list: Any) -> List[str]:
    if not isinstance(raw_list, list):
        return ["Casual"]
    out: List[str] = []
    for item in raw_list:
        v = _norm(str(item))
        if not v:
            continue
        hit = None
        for alias, canonical in sorted(_OCCASION_ALIASES.items(), key=lambda t: len(t[0]), reverse=True):
            if alias in v:
                hit = canonical
                break
        if not hit:
            hit = _closest(v, OCCASIONS)
        if hit and hit not in out:
            out.append(hit)
    return out or ["Casual"]


def normalize_season(raw: Optional[str]) -> str:
    v = _norm(raw or "")
    if not v:
        return "All-Season"
    for alias, canonical in _SEASON_ALIASES.items():
        if alias in v:
            return canonical
    match = _closest(v, SEASONS)
    return match or "All-Season"


def normalize_tags(raw_list: Any, limit: int = 8) -> List[str]:
    """Clean free-form style/attribute tags (kept as text, not controlled)."""
    if not isinstance(raw_list, list):
        return []
    out: List[str] = []
    for item in raw_list:
        tag = re.sub(r"[^a-zA-Z0-9 \-&']", "", str(item)).strip()
        if tag and len(tag) <= 40 and tag.lower() not in {t.lower() for t in out}:
            out.append(tag)
        if len(out) >= limit:
            break
    return out


def clamp_confidence(raw: Any) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, value))


def normalize_wardrobe_analysis(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Validate + normalize the vision model's structured wardrobe output.

    This is the single boundary between untrusted model text and controlled
    persistence fields: every returned value is collapsed onto the platform
    taxonomy here and only here.
    """
    if not isinstance(raw, dict):
        raise ValueError("Wardrobe analysis must be a JSON object")

    subcat = str(raw.get("item_type") or raw.get("detected_subcategory") or "").strip() or None
    category = normalize_category(raw.get("category") or raw.get("detected_category"), subcat)
    family = normalize_color(raw.get("primary_color") or raw.get("detected_color"))

    secondary_raw = raw.get("secondary_colors")
    secondary = []
    if isinstance(secondary_raw, list):
        secondary = [normalize_color(c) for c in secondary_raw if str(c).strip()]
        secondary = [c for c in dict.fromkeys(secondary) if c != family]

    occasions = normalize_occasions(
        raw.get("occasion_suitability") or raw.get("suggested_occasions")
    )
    style_tags = normalize_tags(raw.get("style_tags") or raw.get("ai_tags"))
    style = str(raw.get("style") or raw.get("detected_style") or "").strip()

    return {
        "category": category,
        "item_type": subcat,
        "primary_color": family,
        "primary_color_hex": color_hex_for_family(family, raw.get("primary_color_hex") or raw.get("detected_color_hex")),
        "secondary_colors": secondary,
        "style": style,
        "style_tags": style_tags,
        "pattern": normalize_pattern(raw.get("pattern") or raw.get("detected_pattern")),
        "occasion_suitability": occasions,
        "seasonality": normalize_season(raw.get("seasonality")),
        "confidence": clamp_confidence(raw.get("confidence")),
    }
