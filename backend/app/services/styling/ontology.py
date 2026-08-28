from enum import Enum
from typing import Dict, Any, Set, Tuple
from dataclasses import dataclass, field


class SlotType(str, Enum):
    # Upper Body Slots
    FORMAL_OUTER = "formal_outer"               # blazer, suit jacket, formal coat
    SEMI_FORMAL_OUTER = "semi_formal_outer"     # sport coat, cardigan, smart sweater jacket
    CASUAL_OUTER = "casual_outer"               # casual jacket, hoodie, denim jacket
    FORMAL_SHIRT = "formal_shirt"               # dress shirt, tuxedo shirt, silk dress blouse
    CASUAL_SHIRT = "casual_shirt"               # casual button-up, linen shirt, polo, henley
    KNIT_LAYER = "knit_layer"                   # sweater, pullover, cardigan
    T_SHIRT = "t_shirt"                         # basic tee, graphic tee
    INNER_LAYER = "inner_layer"                 # undershirt, silk camisole

    # Lower Body Slots
    FORMAL_BOTTOM = "formal_bottom"             # suit trousers, dress pants, tuxedo trousers
    SEMI_FORMAL_BOTTOM = "semi_formal_bottom"   # tailored chinos, smart wool trousers
    CASUAL_BOTTOM = "casual_bottom"             # casual chinos, denim, jeans, joggers
    SHORTS = "shorts"                           # tailored shorts, casual shorts
    ACTIVEWEAR_BOTTOM = "activewear_bottom"     # track pants, athletic tights

    # Footwear Slots
    FORMAL_SHOES = "formal_shoes"               # oxford, derby, dress monk strap
    SEMI_FORMAL_SHOES = "semi_formal_shoes"     # penny loafers, dress derbies, heeled sandals
    CASUAL_SHOES = "casual_shoes"               # minimalist leather sneakers, slip-ons
    BOOTS = "boots"                             # chelsea boots, chukka boots
    ATHLETIC_SHOES = "athletic_shoes"           # running sneakers, training shoes
    SANDALS = "sandals"                         # dress sandals, slides

    # One-Piece Slots
    DRESS = "dress"                             # silk slip column dress, maxi gown, cocktail dress
    SUIT = "suit"                               # two-piece or three-piece suit
    JUMPSUIT = "jumpsuit"                       # tailored jumpsuit

    # Accessories Slots
    TIE = "tie"                                 # necktie, bow tie
    BELT = "belt"                               # dress belt, casual belt
    WATCH = "watch"                             # dress watch, chronograph, casual watch
    POCKET_SQUARE = "pocket_square"             # silk pocket square
    SCARF = "scarf"                             # cashmere scarf, silk scarf
    HAT = "hat"                                 # fedora, panama hat, cap
    BAG = "bag"                                 # minaudiere clutch, briefcase, tote
    JEWELRY = "jewelry"                         # cufflinks, bracelet, necklace
    EYEWEAR = "eyewear"                         # sunglasses


class FormalityLevel(int, Enum):
    ACTIVE = 0
    CASUAL = 1
    SMART_CASUAL = 2
    COCKTAIL = 3
    BUSINESS_FORMAL = 4
    FORMAL = 5
    BLACK_TIE = 6


@dataclass
class SlotDefinition:
    slot_type: SlotType
    label: str
    layer_order: int  # 1: base, 2: top/shirt, 3: mid-layer, 4: outerwear, 5: overcoat, 10: bottom, 20: footwear, 30: accessory
    default_formality: FormalityLevel
    compatible_slots: Set[SlotType] = field(default_factory=set)
    incompatible_slots: Set[SlotType] = field(default_factory=set)
    color_role: str = "neutral"  # "anchor_neutral", "primary", "accent", "leather_match"


SLOT_DEFINITIONS: Dict[SlotType, SlotDefinition] = {
    # Upper
    SlotType.FORMAL_OUTER: SlotDefinition(
        slot_type=SlotType.FORMAL_OUTER,
        label="Tailored Blazer / Formal Jacket",
        layer_order=4,
        default_formality=FormalityLevel.FORMAL,
        compatible_slots={SlotType.FORMAL_SHIRT, SlotType.FORMAL_BOTTOM, SlotType.FORMAL_SHOES, SlotType.TIE, SlotType.POCKET_SQUARE, SlotType.BELT, SlotType.WATCH},
        incompatible_slots={SlotType.ATHLETIC_SHOES, SlotType.ACTIVEWEAR_BOTTOM, SlotType.CASUAL_OUTER},
        color_role="anchor_neutral"
    ),
    SlotType.SEMI_FORMAL_OUTER: SlotDefinition(
        slot_type=SlotType.SEMI_FORMAL_OUTER,
        label="Smart Casual Jacket / Summer Blazer",
        layer_order=4,
        default_formality=FormalityLevel.SMART_CASUAL,
        compatible_slots={SlotType.CASUAL_SHIRT, SlotType.FORMAL_SHIRT, SlotType.SEMI_FORMAL_BOTTOM, SlotType.SEMI_FORMAL_SHOES, SlotType.CASUAL_SHOES, SlotType.WATCH},
        incompatible_slots={SlotType.ACTIVEWEAR_BOTTOM, SlotType.ATHLETIC_SHOES},
        color_role="primary"
    ),
    SlotType.CASUAL_OUTER: SlotDefinition(
        slot_type=SlotType.CASUAL_OUTER,
        label="Casual Jacket / Layer",
        layer_order=4,
        default_formality=FormalityLevel.CASUAL,
        compatible_slots={SlotType.T_SHIRT, SlotType.CASUAL_SHIRT, SlotType.CASUAL_BOTTOM, SlotType.CASUAL_SHOES},
        incompatible_slots={SlotType.FORMAL_BOTTOM, SlotType.TIE, SlotType.FORMAL_SHOES},
        color_role="primary"
    ),
    SlotType.FORMAL_SHIRT: SlotDefinition(
        slot_type=SlotType.FORMAL_SHIRT,
        label="Formal Dress Shirt / Silk Blouse",
        layer_order=2,
        default_formality=FormalityLevel.FORMAL,
        compatible_slots={SlotType.FORMAL_OUTER, SlotType.FORMAL_BOTTOM, SlotType.FORMAL_SHOES, SlotType.TIE, SlotType.POCKET_SQUARE},
        incompatible_slots={SlotType.ATHLETIC_SHOES, SlotType.ACTIVEWEAR_BOTTOM},
        color_role="primary"
    ),
    SlotType.CASUAL_SHIRT: SlotDefinition(
        slot_type=SlotType.CASUAL_SHIRT,
        label="Linen / Button-Up Shirt",
        layer_order=2,
        default_formality=FormalityLevel.SMART_CASUAL,
        compatible_slots={SlotType.SEMI_FORMAL_OUTER, SlotType.SEMI_FORMAL_BOTTOM, SlotType.CASUAL_BOTTOM, SlotType.SEMI_FORMAL_SHOES, SlotType.CASUAL_SHOES},
        incompatible_slots={SlotType.TIE},
        color_role="primary"
    ),
    SlotType.KNIT_LAYER: SlotDefinition(
        slot_type=SlotType.KNIT_LAYER,
        label="Cashmere / Fine Knitwear",
        layer_order=3,
        default_formality=FormalityLevel.SMART_CASUAL,
        compatible_slots={SlotType.SEMI_FORMAL_BOTTOM, SlotType.CASUAL_BOTTOM, SlotType.SEMI_FORMAL_SHOES, SlotType.CASUAL_SHOES},
        incompatible_slots={SlotType.TIE},
        color_role="primary"
    ),
    SlotType.T_SHIRT: SlotDefinition(
        slot_type=SlotType.T_SHIRT,
        label="Organic Cotton T-Shirt",
        layer_order=2,
        default_formality=FormalityLevel.CASUAL,
        compatible_slots={SlotType.CASUAL_OUTER, SlotType.CASUAL_BOTTOM, SlotType.CASUAL_SHOES},
        incompatible_slots={SlotType.FORMAL_OUTER, SlotType.FORMAL_BOTTOM, SlotType.FORMAL_SHOES, SlotType.TIE},
        color_role="neutral"
    ),

    # Lower
    SlotType.FORMAL_BOTTOM: SlotDefinition(
        slot_type=SlotType.FORMAL_BOTTOM,
        label="Tailored Suit Trousers",
        layer_order=10,
        default_formality=FormalityLevel.FORMAL,
        compatible_slots={SlotType.FORMAL_OUTER, SlotType.FORMAL_SHIRT, SlotType.FORMAL_SHOES, SlotType.BELT, SlotType.TIE},
        incompatible_slots={SlotType.ATHLETIC_SHOES, SlotType.T_SHIRT, SlotType.CASUAL_OUTER},
        color_role="anchor_neutral"
    ),
    SlotType.SEMI_FORMAL_BOTTOM: SlotDefinition(
        slot_type=SlotType.SEMI_FORMAL_BOTTOM,
        label="Pleated Chinos / Tailored Trousers",
        layer_order=10,
        default_formality=FormalityLevel.SMART_CASUAL,
        compatible_slots={SlotType.FORMAL_OUTER, SlotType.SEMI_FORMAL_OUTER, SlotType.CASUAL_SHIRT, SlotType.FORMAL_SHIRT, SlotType.KNIT_LAYER, SlotType.SEMI_FORMAL_SHOES, SlotType.BELT},
        incompatible_slots={SlotType.ATHLETIC_SHOES},
        color_role="anchor_neutral"
    ),
    SlotType.CASUAL_BOTTOM: SlotDefinition(
        slot_type=SlotType.CASUAL_BOTTOM,
        label="Relaxed Trousers / Denim",
        layer_order=10,
        default_formality=FormalityLevel.CASUAL,
        compatible_slots={SlotType.CASUAL_OUTER, SlotType.CASUAL_SHIRT, SlotType.KNIT_LAYER, SlotType.T_SHIRT, SlotType.CASUAL_SHOES, SlotType.SEMI_FORMAL_SHOES},
        incompatible_slots={SlotType.FORMAL_OUTER, SlotType.FORMAL_SHOES, SlotType.TIE},
        color_role="anchor_neutral"
    ),

    # Footwear
    SlotType.FORMAL_SHOES: SlotDefinition(
        slot_type=SlotType.FORMAL_SHOES,
        label="Goodyear-Welted Oxford / Dress Shoes",
        layer_order=20,
        default_formality=FormalityLevel.FORMAL,
        compatible_slots={SlotType.FORMAL_OUTER, SlotType.FORMAL_SHIRT, SlotType.FORMAL_BOTTOM, SlotType.BELT},
        incompatible_slots={SlotType.T_SHIRT, SlotType.CASUAL_BOTTOM, SlotType.ACTIVEWEAR_BOTTOM},
        color_role="leather_match"
    ),
    SlotType.SEMI_FORMAL_SHOES: SlotDefinition(
        slot_type=SlotType.SEMI_FORMAL_SHOES,
        label="Calfskin Penny Loafers / Derbies / Strappy Heels",
        layer_order=20,
        default_formality=FormalityLevel.SMART_CASUAL,
        compatible_slots={SlotType.SEMI_FORMAL_OUTER, SlotType.CASUAL_SHIRT, SlotType.KNIT_LAYER, SlotType.SEMI_FORMAL_BOTTOM, SlotType.DRESS},
        incompatible_slots={SlotType.ACTIVEWEAR_BOTTOM},
        color_role="leather_match"
    ),
    SlotType.CASUAL_SHOES: SlotDefinition(
        slot_type=SlotType.CASUAL_SHOES,
        label="Minimalist Low-Top Leather Sneakers",
        layer_order=20,
        default_formality=FormalityLevel.CASUAL,
        compatible_slots={SlotType.SEMI_FORMAL_OUTER, SlotType.CASUAL_SHIRT, SlotType.KNIT_LAYER, SlotType.T_SHIRT, SlotType.CASUAL_BOTTOM, SlotType.SEMI_FORMAL_BOTTOM},
        incompatible_slots={SlotType.FORMAL_BOTTOM, SlotType.FORMAL_OUTER, SlotType.TIE},
        color_role="neutral"
    ),

    # One-Piece
    SlotType.DRESS: SlotDefinition(
        slot_type=SlotType.DRESS,
        label="Silk Maxi Dress / Evening Gown",
        layer_order=2,
        default_formality=FormalityLevel.FORMAL,
        compatible_slots={SlotType.SEMI_FORMAL_SHOES, SlotType.BAG, SlotType.JEWELRY, SlotType.POCKET_SQUARE},
        incompatible_slots={SlotType.FORMAL_BOTTOM, SlotType.CASUAL_BOTTOM, SlotType.T_SHIRT, SlotType.FORMAL_SHIRT},
        color_role="primary"
    ),

    # Accessories
    SlotType.TIE: SlotDefinition(
        slot_type=SlotType.TIE,
        label="Mulberry Silk Twill Tie",
        layer_order=30,
        default_formality=FormalityLevel.FORMAL,
        compatible_slots={SlotType.FORMAL_OUTER, SlotType.FORMAL_SHIRT, SlotType.FORMAL_BOTTOM, SlotType.FORMAL_SHOES},
        incompatible_slots={SlotType.T_SHIRT, SlotType.KNIT_LAYER, SlotType.CASUAL_SHOES},
        color_role="accent"
    ),
    SlotType.POCKET_SQUARE: SlotDefinition(
        slot_type=SlotType.POCKET_SQUARE,
        label="Silk Pocket Square",
        layer_order=30,
        default_formality=FormalityLevel.FORMAL,
        compatible_slots={SlotType.FORMAL_OUTER, SlotType.SEMI_FORMAL_OUTER, SlotType.DRESS},
        incompatible_slots=set(),
        color_role="accent"
    ),
    SlotType.BELT: SlotDefinition(
        slot_type=SlotType.BELT,
        label="Italian Full-Grain Leather Belt",
        layer_order=30,
        default_formality=FormalityLevel.FORMAL,
        compatible_slots={SlotType.FORMAL_BOTTOM, SlotType.SEMI_FORMAL_BOTTOM, SlotType.FORMAL_SHOES, SlotType.SEMI_FORMAL_SHOES},
        incompatible_slots=set(),
        color_role="leather_match"
    ),
    SlotType.BAG: SlotDefinition(
        slot_type=SlotType.BAG,
        label="Evening Minaudiere Clutch / Leather Bag",
        layer_order=30,
        default_formality=FormalityLevel.FORMAL,
        compatible_slots={SlotType.DRESS, SlotType.FORMAL_OUTER, SlotType.SEMI_FORMAL_OUTER},
        incompatible_slots=set(),
        color_role="accent"
    ),
    SlotType.WATCH: SlotDefinition(
        slot_type=SlotType.WATCH,
        label="Chronograph Leather Watch",
        layer_order=30,
        default_formality=FormalityLevel.FORMAL,
        compatible_slots={SlotType.FORMAL_OUTER, SlotType.SEMI_FORMAL_OUTER, SlotType.CASUAL_SHIRT, SlotType.FORMAL_SHIRT},
        incompatible_slots=set(),
        color_role="accent"
    )
}


def classify_product_slot(product: Any) -> Tuple[SlotType, FormalityLevel]:
    """Deterministically classifies any catalog Product into its primary slot and formality level."""
    cat_slug = (product.category.slug.lower() if hasattr(product, "category") and product.category else "")
    title = product.title.lower()
    style_tags = product.style_tags or "[]"

    # Outerwear
    if "outer" in cat_slug or "blazer" in title or "coat" in title or "jacket" in title:
        if "tuxedo" in title or "wool double-breasted" in title or "formal" in style_tags:
            return SlotType.FORMAL_OUTER, FormalityLevel.FORMAL
        elif "linen" in title or "summer" in title or "smart_casual" in style_tags:
            return SlotType.SEMI_FORMAL_OUTER, FormalityLevel.SMART_CASUAL
        return SlotType.CASUAL_OUTER, FormalityLevel.CASUAL

    # Tops
    if "top" in cat_slug or "shirt" in cat_slug:
        if "poplin" in title or "dress shirt" in title or "silk" in title or "french cuff" in title:
            return SlotType.FORMAL_SHIRT, FormalityLevel.FORMAL
        elif "linen" in title or "button" in title:
            return SlotType.CASUAL_SHIRT, FormalityLevel.SMART_CASUAL
        elif "sweater" in title or "knit" in title or "funnel" in title:
            return SlotType.KNIT_LAYER, FormalityLevel.SMART_CASUAL
        elif "t-shirt" in title or "tee" in title:
            return SlotType.T_SHIRT, FormalityLevel.CASUAL
        return SlotType.FORMAL_SHIRT, FormalityLevel.SMART_CASUAL

    # Bottoms
    if "bottom" in cat_slug or "trouser" in title or "chino" in title or "pant" in title or "skirt" in title:
        if "suit trouser" in title or "tuxedo" in title or "pleated" in title or "virgin wool" in title or "formal" in style_tags:
            return SlotType.FORMAL_BOTTOM, FormalityLevel.FORMAL
        elif "chino" in title or "wide-leg" in title or "wool trouser" in title:
            return SlotType.SEMI_FORMAL_BOTTOM, FormalityLevel.SMART_CASUAL
        elif "denim" in title or "jean" in title:
            return SlotType.CASUAL_BOTTOM, FormalityLevel.CASUAL
        return SlotType.SEMI_FORMAL_BOTTOM, FormalityLevel.SMART_CASUAL

    # Dresses
    if "dress" in cat_slug or "dress" in title or "gown" in title:
        return SlotType.DRESS, FormalityLevel.FORMAL

    # Footwear
    if "footwear" in cat_slug or "shoe" in cat_slug or "oxford" in title or "loafer" in title or "sandal" in title or "derby" in title or "sneaker" in title:
        if "oxford" in title or "goodyear" in title:
            return SlotType.FORMAL_SHOES, FormalityLevel.FORMAL
        elif "loafer" in title or "derby" in title or "sandal" in title or "heel" in title:
            return SlotType.SEMI_FORMAL_SHOES, FormalityLevel.SMART_CASUAL
        elif "sneaker" in title:
            return SlotType.CASUAL_SHOES, FormalityLevel.CASUAL
        return SlotType.SEMI_FORMAL_SHOES, FormalityLevel.SMART_CASUAL

    # Accessories
    if "access" in cat_slug or "tie" in title or "pocket" in title or "belt" in title or "clutch" in title or "watch" in title:
        if "tie" in title:
            return SlotType.TIE, FormalityLevel.FORMAL
        elif "pocket" in title:
            return SlotType.POCKET_SQUARE, FormalityLevel.FORMAL
        elif "belt" in title:
            return SlotType.BELT, FormalityLevel.FORMAL
        elif "clutch" in title or "bag" in title:
            return SlotType.BAG, FormalityLevel.FORMAL
        elif "watch" in title:
            return SlotType.WATCH, FormalityLevel.FORMAL

    return SlotType.CASUAL_SHIRT, FormalityLevel.CASUAL
