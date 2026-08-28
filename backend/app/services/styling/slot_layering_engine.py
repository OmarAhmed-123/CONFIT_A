from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass


@dataclass
class SlotResolutionResult:
    """Structured output contract emitted by the Slot Rules & Layering Engine."""
    normalized_slot: str
    applied_item: Optional[Dict[str, Any]]
    replaced_items: List[Dict[str, Any]]
    removed_conflicts: List[Dict[str, Any]]
    final_applied_items: List[Dict[str, Any]]
    final_slot_map: Dict[str, int]
    resolved_layer_order: List[str]
    warnings: List[str]
    unsupported_reason: Optional[str]
    support_level: str  # "supported", "preview_limited", "unsupported"
    requires_render: bool
    truthfulness_flags: Dict[str, bool]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "normalized_slot": self.normalized_slot,
            "applied_item": self.applied_item,
            "replaced_items": self.replaced_items,
            "removed_conflicts": self.removed_conflicts,
            "final_applied_items": self.final_applied_items,
            "final_slot_map": self.final_slot_map,
            "resolved_layer_order": self.resolved_layer_order,
            "warnings": self.warnings,
            "unsupported_reason": self.unsupported_reason,
            "support_level": self.support_level,
            "requires_render": self.requires_render,
            "truthfulness_flags": self.truthfulness_flags
        }


class SlotLayeringEngine:
    """Production-Grade Slot Rules, Conflict Resolution & Garment Layering Engine.
    Enforces normalized body slot mapping, strict category exclusivity, dress override logic,
    anatomical layer ordering, and honest limitation handling across frontend and backend.
    """

    LAYER_HIERARCHY: Dict[str, int] = {
        "inner_layer": 1,
        "upper_inner": 2,
        "dress": 2,
        "full_body": 2,
        "knit_layer": 3,
        "upper_outer": 4,
        "lower": 10,
        "footwear": 20,
        "accessory_waist": 30,
        "accessory_neck": 30,
        "accessory_hand": 30,
        "accessory_light": 30,
        "accessory": 30
    }

    @classmethod
    def map_category_to_slot(cls, product: Any) -> Tuple[str, int, str]:
        """Classifies any catalog product into normalized slot, layer order, and support level."""
        cat_slug = (getattr(product.category, "slug", "") if hasattr(product, "category") and product.category else "").lower()
        title = (getattr(product, "title", "") or "").lower()

        # Check unsupported/deferred categories
        if "hat" in title or "cap" in title or "helmet" in title:
            return "accessory_head", 30, "unsupported"

        # Dresses & Jumpsuits (Full Body)
        if "dress" in cat_slug or "dress" in title or "gown" in title or "jumpsuit" in title:
            return "full_body", 2, "supported"

        # Outerwear (Upper Outer)
        if "outer" in cat_slug or "blazer" in title or "jacket" in title or "coat" in title or "tuxedo" in title:
            return "upper_outer", 4, "supported"

        # Tops & Shirts (Upper Inner)
        if "top" in cat_slug or "shirt" in cat_slug or "sweater" in title or "knit" in title or "blouse" in title or "polo" in title or "tee" in title or "t-shirt" in title:
            return "upper_inner", 2, "supported"

        # Bottoms & Trousers (Lower)
        if "bottom" in cat_slug or "trouser" in title or "chino" in title or "denim" in title or "pant" in title or "skirt" in title or "shorts" in title:
            return "lower", 10, "supported"

        # Footwear
        if "footwear" in cat_slug or "shoe" in cat_slug or "oxford" in title or "loafer" in title or "sandal" in title or "sneaker" in title or "boot" in title or "heel" in title:
            return "footwear", 20, "supported"

        # Accessories
        if "belt" in title:
            return "accessory_waist", 30, "preview_limited"
        if "tie" in title or "scarf" in title or "pocket" in title:
            return "accessory_neck", 30, "supported"
        if "clutch" in title or "bag" in title:
            return "accessory_hand", 30, "preview_limited"
        if "watch" in title:
            return "accessory_light", 30, "preview_limited"

        return "upper_inner", 2, "supported"

    @classmethod
    def resolve_and_apply(
        cls,
        existing_items: List[Dict[str, Any]],
        new_product: Any,
        target_slot_override: Optional[str] = None
    ) -> SlotResolutionResult:
        slot, layer_order, support_level = cls.map_category_to_slot(new_product)
        effective_slot = target_slot_override or slot

        warnings = []
        replaced_items = []
        removed_conflicts = []

        truthfulness_flags = {
            "is_supported": support_level == "supported",
            "is_preview_limited": support_level == "preview_limited",
            "is_unsupported": support_level == "unsupported",
            "conflict_cleared": False
        }

        # Check unsupported categories (e.g. headwear deferred for facial identity protection)
        if support_level == "unsupported":
            unsupported_reason = f"Category for '{new_product.title}' is currently deferred from 3D try-on to guarantee 100% facial identity preservation."
            warnings.append(unsupported_reason)
            return SlotResolutionResult(
                normalized_slot=effective_slot,
                applied_item=None,
                replaced_items=[],
                removed_conflicts=[],
                final_applied_items=existing_items,
                final_slot_map={it["position"]: it["product_id"] for it in existing_items},
                resolved_layer_order=[it["position"] for it in existing_items],
                warnings=warnings,
                unsupported_reason=unsupported_reason,
                support_level="unsupported",
                requires_render=False,
                truthfulness_flags=truthfulness_flags
            )

        # Build new applied item dictionary
        first_sku = new_product.skus[0] if hasattr(new_product, "skus") and new_product.skus else None
        rec_size = first_sku.size if first_sku else "M"

        new_item_dict = {
            "product_id": new_product.id,
            "product_title": new_product.title,
            "brand_name": new_product.brand.brand_name if hasattr(new_product, "brand") and new_product.brand else "CONFIT Partner",
            "category_name": new_product.category.name if hasattr(new_product, "category") and new_product.category else "Apparel",
            "position": "dress" if effective_slot == "full_body" else effective_slot,
            "slot_type": effective_slot,
            "image_url": new_product.thumbnail_url,
            "color_family": getattr(new_product, "color_family", "Neutral"),
            "color_hex": getattr(new_product, "dominant_hex", "#1B1F3B"),
            "material": getattr(new_product, "material", "Fine Fabric"),
            "price": float(new_product.base_price),
            "selected_size": rec_size,
            "layer_order": layer_order
        }

        # Conflict Resolution & Replacement Engine
        surviving_items = []

        is_full_body_drop = (effective_slot in ["full_body", "dress"])

        for it in existing_items:
            it_slot = it.get("slot_type") or it.get("position")
            it_id = it.get("product_id")

            # Duplicate prevention: If same item already applied, skip duplicate
            if it_id == new_product.id:
                replaced_items.append(it)
                continue

            # Dress Exclusivity: Dress overrides separate tops and bottoms
            if is_full_body_drop and it_slot in ["upper_inner", "lower"]:
                removed_conflicts.append(it)
                truthfulness_flags["conflict_cleared"] = True
                warnings.append(f"Full-body dress replaced conflicting {it_slot.replace('_', ' ')} '{it.get('product_title')}'.")
                continue

            # Top or Bottom drop overrides existing full-body dress
            if effective_slot in ["upper_inner", "lower"] and it_slot in ["full_body", "dress"]:
                removed_conflicts.append(it)
                truthfulness_flags["conflict_cleared"] = True
                warnings.append(f"Applying separate {effective_slot} cleared full-body dress '{it.get('product_title')}'.")
                continue

            # Exclusive slot replacement: same slot gets replaced
            if it_slot == effective_slot or (it_slot == "dress" and is_full_body_drop):
                replaced_items.append(it)
                continue

            surviving_items.append(it)

        surviving_items.append(new_item_dict)

        # Sort strictly by anatomical layer order
        surviving_items.sort(key=lambda it: cls.LAYER_HIERARCHY.get(it.get("slot_type") or it.get("position"), 10))

        final_slot_map = {(it.get("slot_type") or it.get("position")): it["product_id"] for it in surviving_items}
        resolved_layer_order = [(it.get("slot_type") or it.get("position")) for it in surviving_items]

        return SlotResolutionResult(
            normalized_slot=effective_slot,
            applied_item=new_item_dict,
            replaced_items=replaced_items,
            removed_conflicts=removed_conflicts,
            final_applied_items=surviving_items,
            final_slot_map=final_slot_map,
            resolved_layer_order=resolved_layer_order,
            warnings=warnings,
            unsupported_reason=None,
            support_level=support_level,
            requires_render=True,
            truthfulness_flags=truthfulness_flags
        )

    @classmethod
    def resolve_and_remove(
        cls,
        existing_items: List[Dict[str, Any]],
        product_id: Optional[int] = None,
        slot: Optional[str] = None
    ) -> SlotResolutionResult:
        remaining_items = []
        removed = []

        for it in existing_items:
            it_slot = it.get("slot_type") or it.get("position")
            it_id = it.get("product_id")

            if product_id and it_id == product_id:
                removed.append(it)
                continue
            if slot and it_slot == slot:
                removed.append(it)
                continue

            remaining_items.append(it)

        remaining_items.sort(key=lambda it: cls.LAYER_HIERARCHY.get(it.get("slot_type") or it.get("position"), 10))
        final_slot_map = {(it.get("slot_type") or it.get("position")): it["product_id"] for it in remaining_items}
        resolved_layer_order = [(it.get("slot_type") or it.get("position")) for it in remaining_items]

        return SlotResolutionResult(
            normalized_slot=slot or "removed",
            applied_item=None,
            replaced_items=[],
            removed_conflicts=removed,
            final_applied_items=remaining_items,
            final_slot_map=final_slot_map,
            resolved_layer_order=resolved_layer_order,
            warnings=[],
            unsupported_reason=None,
            support_level="supported",
            requires_render=True,
            truthfulness_flags={"is_supported": True, "conflict_cleared": False}
        )

    @classmethod
    def reorder_layers(cls, existing_items: List[Dict[str, Any]], slot_order: List[str]) -> List[Dict[str, Any]]:
        order_map = {slot: idx for idx, slot in enumerate(slot_order)}
        return sorted(existing_items, key=lambda it: order_map.get(it.get("position", ""), 99))
