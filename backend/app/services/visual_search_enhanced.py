"""
Deterministic Visual Search Enhancement Module

This module provides enhanced visual search capabilities using deterministic
algorithms only. No ML models, no embeddings, no vector databases.

Enhancements:
A. Synonym normalization
B. Category hierarchy matching
C. Color similarity (LAB color space)
D. Style/tag weighting
E. Evidence-based scoring
"""

from typing import Dict, List, Optional, Set, Tuple
import math


# =============================================================================
# A. SYNONYM NORMALIZATION
# =============================================================================

# Controlled fashion taxonomy - synonyms map to canonical forms
SYNONYM_MAP: Dict[str, str] = {
    # Tops
    "tee": "t-shirt",
    "tshirt": "t-shirt",
    "t shirt": "t-shirt",
    "blouse": "blouse",
    "shirt": "shirt",
    "sweater": "sweater",
    "pullover": "sweater",
    "jumper": "sweater",
    "cardigan": "cardigan",
    "hoodie": "hoodie",
    
    # Bottoms
    "trousers": "pants",
    "slacks": "pants",
    "jeans": "jeans",
    "denim": "jeans",
    "shorts": "shorts",
    "skirt": "skirt",
    
    # Dresses
    "frock": "dress",
    "gown": "dress",
    "sundress": "dress",
    "cocktail dress": "dress",
    
    # Outerwear
    "jacket": "jacket",
    "blazer": "blazer",
    "coat": "coat",
    "vest": "vest",
    "waistcoat": "vest",
    
    # Footwear
    "shoes": "shoes",
    "sneakers": "sneakers",
    "trainers": "sneakers",
    "kicks": "sneakers",
    "boots": "boots",
    "sandals": "sandals",
    "heels": "heels",
    "stilettos": "heels",
    
    # Accessories
    "bag": "bag",
    "purse": "bag",
    "handbag": "bag",
    "hat": "hat",
    "cap": "hat",
    "scarf": "scarf",
    "belt": "belt",
    "jewelry": "jewelry",
    "jewellery": "jewelry",
}


def normalize_synonym(term: str) -> str:
    """Normalize a term using the synonym map.
    
    Args:
        term: Input term to normalize
        
    Returns:
        Normalized canonical form, or original term if no mapping exists
    """
    if not term:
        return term
    normalized = term.lower().strip()
    return SYNONYM_MAP.get(normalized, normalized)


def expand_synonyms(term: str) -> Set[str]:
    """Expand a term to include all its synonyms.
    
    Args:
        term: Input term to expand
        
    Returns:
        Set of all synonymous terms including the canonical form
    """
    if not term:
        return set()
    
    normalized = term.lower().strip()
    canonical = SYNONYM_MAP.get(normalized, normalized)
    
    # Find all terms that map to the same canonical form
    synonyms = {canonical}
    for syn, canon in SYNONYM_MAP.items():
        if canon == canonical:
            synonyms.add(syn)
    
    return synonyms


# =============================================================================
# B. CATEGORY HIERARCHY
# =============================================================================

# Category hierarchy: parent -> children
CATEGORY_HIERARCHY: Dict[str, Dict] = {
    "tops": {
        "parent": None,
        "children": ["shirt", "blouse", "t-shirt", "sweater", "cardigan", "hoodie", "tank top", "polo"],
        "related": ["outerwear"],  # related categories with weaker match
    },
    "bottoms": {
        "parent": None,
        "children": ["pants", "trousers", "jeans", "shorts", "skirt", "leggings"],
        "related": ["dresses"],
    },
    "dresses": {
        "parent": None,
        "children": ["dress", "gown", "sundress", "cocktail dress", "jumpsuit"],
        "related": ["bottoms"],
    },
    "outerwear": {
        "parent": None,
        "children": ["jacket", "coat", "blazer", "vest", "cardigan"],
        "related": ["tops"],
    },
    "footwear": {
        "parent": None,
        "children": ["shoes", "sneakers", "boots", "sandals", "heels", "loafers"],
        "related": [],
    },
    "accessories": {
        "parent": None,
        "children": ["bag", "hat", "scarf", "belt", "jewelry", "watch", "sunglasses"],
        "related": [],
    },
}


def get_category_match_level(detected_category: str, product_category: str) -> Tuple[float, str]:
    """Determine the match level between detected and product categories.
    
    Args:
        detected_category: Category detected by vision model
        product_category: Product's category name
        
    Returns:
        Tuple of (score_multiplier, match_type)
        - score_multiplier: 1.0 for exact, 0.7 for parent/child, 0.3 for related, 0.0 for no match
        - match_type: "exact", "parent", "child", "related", "none"
    """
    if not detected_category or not product_category:
        return 0.0, "none"
    
    det_lower = detected_category.lower().strip()
    prod_lower = product_category.lower().strip()
    
    # Exact match
    if det_lower == prod_lower:
        return 1.0, "exact"
    
    # Check if product category is a child of detected category
    det_info = CATEGORY_HIERARCHY.get(det_lower, {})
    if prod_lower in det_info.get("children", []):
        return 0.7, "child"
    
    # Check if detected category is a child of product category
    prod_info = CATEGORY_HIERARCHY.get(prod_lower, {})
    if det_lower in prod_info.get("children", []):
        return 0.7, "parent"
    
    # Check related categories — use stricter matching (0.15 instead of 0.3)
    # to prevent unrelated categories from ranking too high
    if prod_lower in det_info.get("related", []) or det_lower in prod_info.get("related", []):
        return 0.15, "related"
    
    return 0.0, "none"


# =============================================================================
# C. COLOR SIMILARITY (LAB Color Space)
# =============================================================================

# Color name to approximate RGB values (simplified)
COLOR_RGB_MAP: Dict[str, Tuple[int, int, int]] = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "navy": (0, 0, 128),
    "dark blue": (0, 0, 139),
    "midnight blue": (25, 25, 112),
    "blue": (0, 0, 255),
    "royal blue": (65, 105, 225),
    "cobalt": (0, 71, 171),
    "red": (255, 0, 0),
    "crimson": (220, 20, 60),
    "scarlet": (255, 36, 0),
    "burgundy": (128, 0, 32),
    "maroon": (128, 0, 0),
    "green": (0, 128, 0),
    "emerald": (80, 200, 120),
    "olive": (128, 128, 0),
    "forest green": (34, 139, 34),
    "lime": (0, 255, 0),
    "yellow": (255, 255, 0),
    "gold": (255, 215, 0),
    "mustard": (255, 219, 88),
    "pink": (255, 192, 203),
    "rose": (255, 0, 127),
    "blush": (255, 111, 97),
    "fuchsia": (255, 0, 255),
    "magenta": (255, 0, 255),
    "purple": (128, 0, 128),
    "violet": (127, 0, 255),
    "lavender": (230, 230, 250),
    "plum": (142, 69, 133),
    "brown": (139, 69, 19),
    "tan": (210, 180, 140),
    "beige": (245, 245, 220),
    "camel": (193, 154, 107),
    "khaki": (240, 230, 140),
    "chocolate": (210, 105, 30),
    "gray": (128, 128, 128),
    "grey": (128, 128, 128),
    "charcoal": (54, 69, 79),
    "slate": (112, 128, 144),
    "silver": (192, 192, 192),
}


def rgb_to_lab(rgb: Tuple[int, int, int]) -> Tuple[float, float, float]:
    """Convert RGB to CIELAB color space.
    
    Uses D65 illuminant reference white.
    
    Args:
        rgb: Tuple of (R, G, B) values 0-255
        
    Returns:
        Tuple of (L, a, b) values
    """
    # Normalize RGB to 0-1
    r, g, b = [x / 255.0 for x in rgb]
    
    # Apply inverse sRGB companding
    def inverse_compand(c):
        if c > 0.04045:
            return ((c + 0.055) / 1.055) ** 2.4
        return c / 12.92
    
    r = inverse_compand(r)
    g = inverse_compand(g)
    b = inverse_compand(b)
    
    # RGB to XYZ (D65 illuminant)
    x = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041
    
    # Normalize by D65 reference white
    x /= 0.95047
    y /= 1.00000
    z /= 1.08883
    
    # XYZ to LAB
    def f(t):
        if t > 0.008856:
            return t ** (1/3)
        return (7.787 * t) + (16 / 116)
    
    fx = f(x)
    fy = f(y)
    fz = f(z)
    
    L = (116 * fy) - 16
    a = 500 * (fx - fy)
    b = 200 * (fy - fz)
    
    return (L, a, b)


def lab_distance(lab1: Tuple[float, float, float], lab2: Tuple[float, float, float]) -> float:
    """Calculate CIE76 color distance between two LAB colors.
    
    Args:
        lab1: First color (L, a, b)
        lab2: Second color (L, a, b)
        
    Returns:
        Euclidean distance in LAB space
    """
    return math.sqrt(
        (lab1[0] - lab2[0]) ** 2 +
        (lab1[1] - lab2[1]) ** 2 +
        (lab1[2] - lab2[2]) ** 2
    )


def get_color_similarity(color1: str, color2: str) -> float:
    """Calculate similarity between two color names.
    
    Args:
        color1: First color name
        color2: Second color name
        
    Returns:
        Similarity score 0.0-1.0 (1.0 = identical, 0.0 = completely different)
    """
    if not color1 or not color2:
        return 0.0
    
    c1_lower = color1.lower().strip()
    c2_lower = color2.lower().strip()
    
    # Exact match
    if c1_lower == c2_lower:
        return 1.0
    
    # Check if colors are in the same family (synonyms)
    color_families = {
        "navy": ["navy", "dark blue", "midnight blue"],
        "blue": ["blue", "royal blue", "cobalt", "azure"],
        "red": ["red", "crimson", "scarlet", "burgundy", "maroon"],
        "green": ["green", "emerald", "olive", "forest green", "lime"],
        "black": ["black", "noir", "ebony"],
        "white": ["white", "ivory", "cream", "off-white", "pearl"],
        "gray": ["gray", "grey", "charcoal", "slate", "silver"],
        "brown": ["brown", "tan", "beige", "camel", "khaki", "chocolate"],
        "pink": ["pink", "rose", "blush", "fuchsia", "magenta"],
        "purple": ["purple", "violet", "lavender", "plum"],
        "yellow": ["yellow", "gold", "mustard", "lemon"],
    }
    
    for family, members in color_families.items():
        if c1_lower in members and c2_lower in members:
            return 0.9  # Same family, slight variation
    
    # Use LAB distance for perceptual similarity
    rgb1 = COLOR_RGB_MAP.get(c1_lower)
    rgb2 = COLOR_RGB_MAP.get(c2_lower)
    
    if rgb1 and rgb2:
        lab1 = rgb_to_lab(rgb1)
        lab2 = rgb_to_lab(rgb2)
        distance = lab_distance(lab1, lab2)
        
        # Convert distance to similarity (0-1)
        # Max possible distance in LAB is ~300, normalize
        similarity = max(0.0, 1.0 - (distance / 300.0))
        return similarity
    
    return 0.0


# =============================================================================
# D. STYLE/TAG WEIGHTING
# =============================================================================

# Style taxonomy with related styles
STYLE_TAXONOMY: Dict[str, Dict] = {
    "casual": {
        "related": ["everyday", "relaxed", "informal", "weekend"],
        "opposite": ["formal", "business"],
    },
    "formal": {
        "related": ["business", "professional", "office", "work"],
        "opposite": ["casual", "streetwear"],
    },
    "smart casual": {
        "related": ["smart", "semi-formal", "business casual"],
        "opposite": [],
    },
    "streetwear": {
        "related": ["urban", "hip-hop", "street", "grunge"],
        "opposite": ["formal", "classic"],
    },
    "bohemian": {
        "related": ["boho", "hippie", "boho-chic", "gypsy"],
        "opposite": ["minimalist", "classic"],
    },
    "minimalist": {
        "related": ["simple", "clean", "basic", "modern"],
        "opposite": ["bohemian", "maximalist"],
    },
    "classic": {
        "related": ["traditional", "timeless", "preppy", "ivy"],
        "opposite": ["streetwear", "avant-garde"],
    },
    "sporty": {
        "related": ["athletic", "active", "gym", "athleisure"],
        "opposite": ["formal"],
    },
    "vintage": {
        "related": ["retro", "antique", "classic"],
        "opposite": ["modern", "contemporary"],
    },
    "romantic": {
        "related": ["feminine", "soft", "delicate", "lace"],
        "opposite": ["streetwear", "minimalist"],
    },
}


def get_style_similarity(style1: str, style2: str) -> float:
    """Calculate similarity between two style descriptors.
    
    Args:
        style1: First style (e.g., from vision model)
        style2: Second style (e.g., from product tags)
        
    Returns:
        Similarity score 0.0-1.0
    """
    if not style1 or not style2:
        return 0.0
    
    s1_lower = style1.lower().strip()
    s2_lower = style2.lower().strip()
    
    # Exact match
    if s1_lower == s2_lower:
        return 1.0
    
    # Check if styles are related
    s1_info = STYLE_TAXONOMY.get(s1_lower, {})
    s2_info = STYLE_TAXONOMY.get(s2_lower, {})
    
    # Check related styles
    if s2_lower in s1_info.get("related", []) or s1_lower in s2_info.get("related", []):
        return 0.7
    
    # Check if one is related to the other's parent
    for related in s1_info.get("related", []):
        if related == s2_lower:
            return 0.7
    
    # Check opposite styles
    if s2_lower in s1_info.get("opposite", []) or s1_lower in s2_info.get("opposite", []):
        return 0.0
    
    return 0.1  # Default: minimal similarity for unrelated styles


# =============================================================================
# E. ENHANCED SCORING
# =============================================================================

# Scoring weights (candidate deterministic weights — to be validated by evaluation)
# These create differentiation between exact matches (high) and partial matches (medium/low)
WEIGHTS = {
    "category_match": 35.0,      # Category is primary signal
    "color_match": 20.0,         # Color is secondary signal
    "style_match": 10.0,         # Style is tertiary signal
    "pattern_match": 5.0,        # Pattern bonus
    "base_score": 20.0,          # Low base — ranking comes from actual matches
    "max_score": 98.0,           # Maximum possible score
}


def calculate_enhanced_score(
    detected_category: Optional[str],
    detected_color: Optional[str],
    detected_style: Optional[str],
    detected_pattern: Optional[str],
    product_category: Optional[str],
    product_color: Optional[str],
    product_style_tags: Optional[str],
    product_title: Optional[str],
    analysis_available: bool = True,
) -> Tuple[float, Dict[str, float]]:
    """Calculate enhanced visual search score using deterministic algorithms.
    
    Args:
        detected_category: Category from vision model
        detected_color: Color from vision model
        detected_style: Style from vision model
        detected_pattern: Pattern from vision model
        product_category: Product's category name
        product_color: Product's color family
        product_style_tags: Product's style tags (comma-separated)
        product_title: Product title for additional matching
        analysis_available: Whether vision analysis was successful
        
    Returns:
        Tuple of (final_score, score_breakdown)
    """
    breakdown = {
        "base": WEIGHTS["base_score"],
        "category": 0.0,
        "color": 0.0,
        "style": 0.0,
        "pattern": 0.0,
    }
    
    if not analysis_available:
        return WEIGHTS["base_score"], breakdown
    
    score = WEIGHTS["base_score"]
    
    # A. Normalize synonyms
    det_cat_normalized = normalize_synonym(detected_category) if detected_category else None
    det_color_normalized = normalize_synonym(detected_color) if detected_color else None
    
    # B. Category hierarchy matching
    if det_cat_normalized and product_category:
        cat_multiplier, cat_type = get_category_match_level(det_cat_normalized, product_category)
        category_score = WEIGHTS["category_match"] * cat_multiplier
        score += category_score
        breakdown["category"] = category_score
        
        # Also check product title for category tokens
        if product_title and cat_multiplier < 1.0:
            title_lower = product_title.lower()
            cat_tokens = det_cat_normalized.lower().split()
            if any(t in title_lower for t in cat_tokens):
                score += WEIGHTS["category_match"] * 0.3  # Partial title match
                breakdown["category"] += WEIGHTS["category_match"] * 0.3
    
    # C. Color similarity
    if det_color_normalized and product_color:
        color_sim = get_color_similarity(det_color_normalized, product_color)
        color_score = WEIGHTS["color_match"] * color_sim
        score += color_score
        breakdown["color"] = color_score
    
    # D. Style matching
    if detected_style and product_style_tags:
        style_tags = [t.strip().lower() for t in product_style_tags.split(",")]
        best_style_sim = 0.0
        for tag in style_tags:
            sim = get_style_similarity(detected_style.lower(), tag)
            best_style_sim = max(best_style_sim, sim)
        
        style_score = WEIGHTS["style_match"] * best_style_sim
        score += style_score
        breakdown["style"] = style_score
    
    # E. Pattern bonus
    if detected_pattern and product_style_tags:
        pattern_lower = detected_pattern.lower()
        tags_lower = product_style_tags.lower()
        if pattern_lower in tags_lower:
            score += WEIGHTS["pattern_match"]
            breakdown["pattern"] = WEIGHTS["pattern_match"]
    
    # Cap at maximum
    final_score = min(WEIGHTS["max_score"], round(score, 1))
    
    return final_score, breakdown
