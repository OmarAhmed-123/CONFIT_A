import json
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.app.models.stylist import Outfit
from backend.app.repositories.stylist_repository import StylistRepository
from backend.app.repositories.catalog_repository import CatalogRepository
from backend.app.services.styling_engine import StylingEngine
from backend.app.services.styling.ontology import classify_product_slot


# Map fine-grained slot ontology values to the coarse canvas positions the
# schema/UI use ("top", "bottom", "outerwear", "footwear", "accessory", "dress").
_SLOT_TO_POSITION = {
    "dress": "dress",
    "suit": "outerwear",
    "jumpsuit": "dress",
    "formal_outer": "outerwear", "semi_formal_outer": "outerwear", "casual_outer": "outerwear",
    "formal_shirt": "top", "casual_shirt": "top", "knit_layer": "top", "t_shirt": "top", "inner_layer": "top",
    "formal_bottom": "bottom", "semi_formal_bottom": "bottom", "casual_bottom": "bottom",
    "shorts": "bottom", "activewear_bottom": "bottom",
    "formal_shoes": "footwear", "semi_formal_shoes": "footwear", "casual_shoes": "footwear",
    "boots": "footwear", "athletic_shoes": "footwear", "sandals": "footwear",
}


def _position_for_product(product) -> str:
    """Derive the canvas position from the shared slot ontology (single source)."""
    slot, _ = classify_product_slot(product)
    return _SLOT_TO_POSITION.get(slot.value, "accessory")


class OutfitService:
    def __init__(self, db: Session):
        self.db = db
        self.stylist_repo = StylistRepository(db)
        self.catalog_repo = CatalogRepository(db)

    def get_public_look(self, share_token: str) -> Optional[Dict[str, Any]]:
        """C8 — public-safe, read-only view of a shared outfit.

        Returns None for unknown/None tokens. The payload deliberately
        contains no user id, no owner identity, no profile data, and no
        internal outfit id — only public outfit content.
        """
        if not share_token:
            return None
        outfit = self.stylist_repo.get_outfit_by_share_token(share_token)
        if not outfit:
            return None
        items = []
        for item in outfit.items:
            product = item.product
            sku = item.sku
            if not product:
                continue
            price = (sku.price_override if sku and sku.price_override else product.base_price)
            items.append({
                "product_title": product.title,
                "brand_name": product.brand.brand_name if product.brand else "CONFIT Partner",
                "category_name": product.category.name if product.category else "Fashion",
                "price": float(price),
                "image_url": product.thumbnail_url,
                "color_hex": (sku.color_hex if sku and sku.color_hex else product.dominant_hex),
                "position": item.position,
            })
        return {
            "title": outfit.title,
            "occasion": outfit.occasion,
            "description": outfit.description,
            "total_price": float(outfit.total_price),
            "compatibility_score": int(outfit.compatibility_score),
            "items": items,
            "created_at": outfit.created_at,
        }

    def evaluate_compatibility(self, product_ids: List[int], target_occasion: str = "Casual") -> Dict[str, Any]:
        products = []
        for pid in product_ids:
            p = self.catalog_repo.get_product_by_id(pid)
            if p:
                products.append({
                    "id": p.id,
                    "title": p.title,
                    "product_title": p.title,
                    "color_family": p.color_family,
                    "dominant_hex": p.dominant_hex,
                    "style_tags": json.loads(p.style_tags) if p.style_tags else [],
                    "occasion_tags": json.loads(p.occasion_tags) if p.occasion_tags else [],
                    "category": p.category.name if p.category else "Apparel",
                    "price": p.base_price,
                    "position": _position_for_product(p),
                    "slot_type": classify_product_slot(p)[0].value,
                })

        return StylingEngine.calculate_compatibility(products, target_occasion=target_occasion)

    def save_outfit(
        self,
        user_id: int,
        title: str,
        occasion: str,
        product_sku_ids: Optional[List[int]] = None,
        product_ids: Optional[List[int]] = None,
        description: Optional[str] = None
    ) -> Outfit:
        """Persist a user-built outfit. Accepts SKU ids and/or product ids; a
        product id resolves to that product's first in-stock SKU (fallback: first
        SKU) so both caller contracts persist a real, purchasable item set."""
        skus = []
        for sku_id in (product_sku_ids or []):
            sku = self.catalog_repo.get_sku_by_id(sku_id)
            if sku:
                skus.append(sku)
        for pid in (product_ids or []):
            product = self.catalog_repo.get_product_by_id(pid)
            if not product or not product.skus:
                continue
            in_stock = [s for s in product.skus if s.is_in_stock and s.stock_level > 0]
            skus.append(in_stock[0] if in_stock else product.skus[0])

        products = []
        items_payload = []
        total_price = 0.0
        hexes = []

        for sku in skus:
            product = sku.product
            if not product:
                continue
            position = _position_for_product(product)
            slot, formality_num = classify_product_slot(product)

            price = sku.price_override or product.base_price
            total_price += price
            hexes.append(sku.color_hex or product.dominant_hex)

            products.append({
                "id": product.id,
                "product_title": product.title,
                "color_family": product.color_family,
                "dominant_hex": product.dominant_hex,
                "style_tags": json.loads(product.style_tags) if product.style_tags else [],
                "occasion_tags": json.loads(product.occasion_tags) if product.occasion_tags else [],
                "position": position,
                "slot_type": slot.value,
                "formality_num": int(formality_num),
                "price": price,
            })

            items_payload.append({
                "product_id": product.id,
                "product_sku_id": sku.id,
                "position": position
            })

        comp = StylingEngine.calculate_compatibility(products, target_occasion=occasion)

        return self.stylist_repo.save_outfit(
            user_id=user_id,
            title=title,
            occasion=occasion,
            compatibility_score=comp["compatibility_score"],
            total_price=total_price,
            color_palette=list(dict.fromkeys(hexes)),
            style_tags=["Curated", occasion],
            items=items_payload,
            is_saved=True,
            is_system_curated=False,
            description=description,
        )

    def _format_outfit(self, o: Outfit) -> Dict[str, Any]:
        items_data = []
        for it in o.items:
            items_data.append({
                "id": it.id,
                "product_id": it.product_id,
                "product_title": it.product.title if it.product else "Garment",
                "brand_name": it.product.brand.brand_name if it.product and it.product.brand else "CONFIT",
                "category_name": it.product.category.name if it.product and it.product.category else "Fashion",
                "price": it.product.base_price if it.product else 0.0,
                "image_url": it.product.thumbnail_url if it.product else "",
                "color_hex": it.product.dominant_hex if it.product else "#1B1F3B",
                "position": it.position,
                "sku_id": it.product_sku_id,
                "selected_size": it.sku.size if it.sku else "M"
            })
        return {
            "id": o.id,
            "title": o.title,
            "description": o.description,
            "occasion": o.occasion,
            "total_price": o.total_price,
            "compatibility_score": o.compatibility_score,
            "color_palette": json.loads(o.color_palette) if o.color_palette else [],
            "style_tags": json.loads(o.style_tags) if o.style_tags else [],
            "is_saved": o.is_saved,
            "is_system_curated": o.is_system_curated,
            "items": items_data,
            "created_at": o.created_at
        }

    def get_outfit_payload(self, outfit_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """Return one formatted outfit, ownership-scoped. None if not found/owned."""
        outfit = self.stylist_repo.get_outfit_by_id(outfit_id)
        if not outfit or outfit.user_id != user_id:
            return None
        return self._format_outfit(outfit)

    def get_user_looks(self, user_id: int) -> List[Dict[str, Any]]:
        outfits = self.stylist_repo.get_user_outfits(user_id, saved_only=True)
        return [self._format_outfit(o) for o in outfits]
