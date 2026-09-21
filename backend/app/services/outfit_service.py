import json
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.app.core.money import to_decimal, money_add, money_mul, to_float
from backend.app.models.stylist import Outfit
from backend.app.repositories.stylist_repository import StylistRepository
from backend.app.repositories.catalog_repository import CatalogRepository
from backend.app.repositories.wardrobe_repository import WardrobeRepository
from backend.app.services.styling_engine import StylingEngine
from backend.app.services.styling.ontology import classify_product_slot
from backend.app.services.styling.composition_policy import (
    CompositionVerdict,
    completeness_status,
    evaluate_composition,
    order_items,
)


class OutfitCompositionError(Exception):
    """Raised when a candidate outfit violates the composition policy.

    Carries the structured verdict so the controller can return an explainable
    422 (code + message + offending slots) instead of an opaque failure.
    """

    def __init__(self, verdict: CompositionVerdict):
        super().__init__(verdict.first_message or "Invalid outfit composition")
        self.verdict = verdict


# Default lifetime of a freshly minted public share link. A share link is an
# unauthenticated read surface, so it expires by default; the owner can always
# mint a new one. 30 days is long enough to be useful and short enough that an
# abandoned link stops working.
DEFAULT_SHARE_TTL_DAYS = 30
MAX_SHARE_TTL_DAYS = 365


def _utcnow() -> datetime:
    """Naive-UTC 'now', matching the DateTime columns in this schema."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


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
        self.wardrobe_repo = WardrobeRepository(db)

    # ------------------------------------------------------------------
    # Share-link lifecycle (OUTFIT-01)
    # ------------------------------------------------------------------
    def _is_share_live(self, outfit: Outfit) -> bool:
        """A token resolves ONLY when minted, not revoked and not expired.

        Possession of the string is deliberately not sufficient — that is the
        whole point of revocation. Callers must not distinguish the three
        failure reasons publicly (all become 404).
        """
        if not outfit.share_token:
            return False
        if getattr(outfit, "share_revoked_at", None):
            return False
        expires_at = getattr(outfit, "share_expires_at", None)
        if expires_at and expires_at <= _utcnow():
            return False
        return True

    def mint_share_token(
        self, outfit: Outfit, ttl_days: int = DEFAULT_SHARE_TTL_DAYS, rotate: bool = False
    ) -> Dict[str, Any]:
        """Create (or return the still-live) public token for an owned outfit.

        Idempotent by default: calling share twice returns the same live link
        instead of littering the table with orphan tokens. ``rotate=True``
        invalidates the previous link and mints a fresh one — the correct
        action when a link leaked.
        """
        ttl_days = max(1, min(int(ttl_days or DEFAULT_SHARE_TTL_DAYS), MAX_SHARE_TTL_DAYS))
        now = _utcnow()

        if rotate or not self._is_share_live(outfit):
            token = f"look_{secrets.token_urlsafe(24)}"
            # Uniqueness is enforced by the unique column; retry on the
            # astronomically unlikely collision rather than trusting luck.
            while self.stylist_repo.get_outfit_by_share_token(token):
                token = f"look_{secrets.token_urlsafe(24)}"
            outfit.share_token = token
            outfit.share_revoked_at = None
            outfit.share_view_count = 0
            outfit.share_expires_at = now + timedelta(days=ttl_days)
            self.db.commit()
            self.db.refresh(outfit)

        return {
            "outfit_id": outfit.id,
            "share_token": outfit.share_token,
            "share_url": f"/looks/{outfit.share_token}",
            "expires_at": outfit.share_expires_at,
            "is_active": self._is_share_live(outfit),
            "view_count": int(outfit.share_view_count or 0),
        }

    def revoke_share_token(self, outfit: Outfit) -> Dict[str, Any]:
        """Revoke the public link. The token is retired, never re-issued."""
        was_live = self._is_share_live(outfit)
        if was_live:
            outfit.share_revoked_at = _utcnow()
            self.db.commit()
        return {
            "outfit_id": outfit.id,
            "revoked": True,
            "was_active": was_live,
            "is_active": False,
        }

    def get_share_state(self, outfit: Outfit) -> Dict[str, Any]:
        """Owner-facing truth about the share link — never an implied claim."""
        live = self._is_share_live(outfit)
        return {
            "outfit_id": outfit.id,
            "is_active": live,
            "share_token": outfit.share_token if live else None,
            "share_url": f"/looks/{outfit.share_token}" if live else None,
            "expires_at": getattr(outfit, "share_expires_at", None) if live else None,
            "revoked_at": getattr(outfit, "share_revoked_at", None),
            "view_count": int(getattr(outfit, "share_view_count", 0) or 0),
        }

    def get_public_look(self, share_token: str) -> Optional[Dict[str, Any]]:
        """C8 — public-safe, read-only view of a shared outfit.

        Returns None for unknown, revoked and expired tokens alike (the caller
        maps all three to an indistinguishable 404, so a probe cannot tell an
        expired link from one that never existed). The payload deliberately
        contains no user id, no owner identity, no profile data, and no
        internal outfit id — only public outfit content.
        """
        if not share_token:
            return None
        outfit = self.stylist_repo.get_outfit_by_share_token(share_token)
        if not outfit or not self._is_share_live(outfit):
            return None
        # Real exposure counter — the owner sees actual opens, not a guess.
        try:
            outfit.share_view_count = int(outfit.share_view_count or 0) + 1
            self.db.commit()
        except Exception:
            self.db.rollback()
        items = []
        for item in outfit.items:
            product = item.product
            sku = item.sku
            if not product:
                continue
            price_raw = to_decimal(sku.price_override if sku and sku.price_override else product.base_price)
            price = to_float(price_raw)
            items.append({
                "product_title": product.title,
                "brand_name": product.brand.brand_name if product.brand else "CONFIT Partner",
                "category_name": product.category.name if product.category else "Fashion",
                "price": price,
                "image_url": product.thumbnail_url,
                "color_hex": (sku.color_hex if sku and sku.color_hex else product.dominant_hex),
                "position": item.position,
            })
        return {
            "title": outfit.title,
            "occasion": outfit.occasion,
            "description": outfit.description,
            "total_price": to_float(outfit.total_price),
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
                    "price": to_float(p.base_price),
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
        skus = self._resolve_skus(product_sku_ids, product_ids)

        products = []
        items_payload = []
        total_price = Decimal("0.00")
        hexes = []

        for sku in skus:
            product = sku.product
            if not product:
                continue
            position = _position_for_product(product)
            slot, formality_num = classify_product_slot(product)

            price = to_decimal(sku.price_override or product.base_price)
            total_price = money_add(total_price, price)
            price_f = to_float(price)
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
                "price": price_f,
            })

            items_payload.append({
                "product_id": product.id,
                "product_sku_id": sku.id,
                "position": position
            })

        # OUTFIT-02: reject an invalid composition BEFORE persisting anything.
        # Previously any SKU set was written, so two pairs of shoes or a
        # duplicated item became a "saved look" the user never composed.
        verdict = evaluate_composition(items_payload)
        if not verdict.is_valid:
            raise OutfitCompositionError(verdict)

        # Canonical layer order (outerwear -> top -> bottom -> footwear ->
        # accessories) is assigned by the shared policy, not by the arbitrary
        # order the client happened to post.
        items_payload = order_items(items_payload)

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

    # ------------------------------------------------------------------
    # Shared helpers (DRY: used by save + replace-items)
    # ------------------------------------------------------------------
    def _resolve_skus(
        self,
        product_sku_ids: Optional[List[int]] = None,
        product_ids: Optional[List[int]] = None,
    ) -> List[Any]:
        """Resolve a mixed SKU/product id payload to real, existing SKU rows.

        Unknown ids are dropped here and surfaced as a composition violation by
        the caller, so a typo can never silently persist a smaller outfit than
        the user believes they saved.
        """
        skus: List[Any] = []
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
        return skus

    def preview_composition(
        self,
        product_sku_ids: Optional[List[int]] = None,
        product_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Dry-run the composition policy without persisting.

        Lets the canvas show *why* a combination will be rejected before the
        user presses Save, using exactly the same rules the write path applies.
        """
        skus = self._resolve_skus(product_sku_ids, product_ids)
        items = [
            {
                "product_id": s.product.id,
                "product_sku_id": s.id,
                "position": _position_for_product(s.product),
            }
            for s in skus
            if s.product
        ]
        verdict = evaluate_composition(items)
        payload = verdict.to_dict()
        payload["resolved_items"] = order_items(items)
        payload["unresolved_ids"] = sorted(
            set(product_sku_ids or []) - {s.id for s in skus}
        )
        return payload

    def replace_outfit_items(
        self,
        outfit: Outfit,
        product_sku_ids: Optional[List[int]] = None,
        product_ids: Optional[List[int]] = None,
    ) -> Outfit:
        """Atomically replace an outfit's item set (canvas edit / reorder).

        The audit found no way to mutate a saved look's contents at all: the
        PATCH endpoint only touched title/occasion/description, so "reopen and
        edit" was impossible. This performs the whole swap — items, price,
        palette and recomputed compatibility — inside ONE transaction, so a
        failure can never leave a half-edited outfit behind.
        """
        skus = self._resolve_skus(product_sku_ids, product_ids)
        products: List[Dict[str, Any]] = []
        items_payload: List[Dict[str, Any]] = []
        total_price = Decimal("0.00")
        hexes: List[str] = []

        for sku in skus:
            product = sku.product
            if not product:
                continue
            position = _position_for_product(product)
            slot, formality_num = classify_product_slot(product)
            price = to_decimal(sku.price_override or product.base_price)
            total_price = money_add(total_price, price)
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
                "price": to_float(price),
            })
            items_payload.append({
                "product_id": product.id,
                "product_sku_id": sku.id,
                "position": position,
            })

        verdict = evaluate_composition(items_payload)
        if not verdict.is_valid:
            raise OutfitCompositionError(verdict)

        items_payload = order_items(items_payload)
        comp = StylingEngine.calculate_compatibility(
            products, target_occasion=outfit.occasion
        )
        return self.stylist_repo.replace_outfit_items(
            outfit_id=outfit.id,
            items=items_payload,
            total_price=total_price,
            compatibility_score=comp["compatibility_score"],
            color_palette=list(dict.fromkeys(hexes)),
        )

    def build_wardrobe_first_outfit(self, user_id: int, occasion: str = "Smart Casual") -> Dict[str, Any]:
        """Group 4 §24 — 'shop your wardrobe first' outfit building.

        Flow: retrieve the caller's ready wardrobe -> pick the best owned item
        per canvas position (occasion + favorite/wear signals, color harmony
        via the existing StylingEngine) -> only canvas positions the wardrobe
        genuinely cannot fill become purchase recommendations from the real
        catalog. Owned items are never re-suggested as purchases (§26).

        Returns a computed (not persisted) look: owned pieces are not catalog
        products, so they cannot be OutfitItem rows — persistence stays with
        save_outfit() for purchasable item sets.
        """
        from backend.app.services import wardrobe_taxonomy as taxonomy

        wardrobe_items = [
            it for it in self.wardrobe_repo.get_user_items(user_id)
            if getattr(it, "processing_status", "ready") == "ready"
        ]

        _CAT_TO_POSITION = {
            "Tops": "top", "Bottoms": "bottom", "Outerwear": "outerwear",
            "Footwear": "footwear", "Accessories": "accessory", "Dresses": "dress",
        }
        positions = ["top", "bottom", "footwear", "outerwear", "accessory"]

        def owned_score(it) -> float:
            """Rank an owned piece for this occasion: explicit occasion match
            dominates, then favorite, then frequency of wear (a proven piece
            beats a neglected one), then neutral-versatile colors."""
            score = 0.0
            item_occasions = json.loads(it.occasions) if it.occasions else []
            occasion_norm = occasion.strip().lower()
            if any(occasion_norm in (o or "").lower() or (o or "").lower() in occasion_norm
                   for o in item_occasions):
                score += 50.0
            if it.is_favorite or it.wear_frequency == "favorite":
                score += 20.0
            if it.wear_frequency == "regular":
                score += 10.0
            elif it.wear_frequency == "rarely_worn":
                score += 4.0   # gently resurface neglected pieces — smart reuse
            score += min(it.wear_count or 0, 10) * 0.5
            if taxonomy.normalize_color(it.color_name) in ("Black", "White", "Navy", "Beige", "Grey", "Ivory"):
                score += 5.0
            return score

        by_position: Dict[str, List[Any]] = {}
        for it in wardrobe_items:
            pos = _CAT_TO_POSITION.get(taxonomy.normalize_category(it.category))
            if pos:
                by_position.setdefault(pos, []).append(it)

        owned_picks: List[Dict[str, Any]] = []
        missing_positions: List[str] = []
        for pos in positions:
            candidates = by_position.get(pos) or []
            if candidates:
                best = max(candidates, key=owned_score)
                owned_picks.append({
                    "position": pos,
                    "source": "owned",
                    "wardrobe_item_id": best.id,
                    "product_title": best.title,
                    "brand_name": best.brand_name,
                    "color_family": taxonomy.normalize_color(best.color_name),
                    "dominant_hex": best.color_hex,
                    "image_url": best.image_url,
                    "price": 0.0,
                    "style_tags": json.loads(best.ai_tags) if best.ai_tags else [],
                    "occasion_tags": json.loads(best.occasions) if best.occasions else [],
                })
            else:
                missing_positions.append(pos)

        # Score the owned combination with the real styling engine so the
        # compatibility number means the same thing as for catalog outfits.
        comp = StylingEngine.calculate_compatibility(owned_picks, target_occasion=occasion) \
            if owned_picks else {"compatibility_score": 0, "is_complete_outfit": False}

        # Only genuine gaps surface purchasable products (never what is owned).
        _POS_TO_SLUG = {"top": "tops", "bottom": "bottoms", "outerwear": "outerwear",
                        "footwear": "footwear", "accessory": "accessories"}
        purchase_suggestions: List[Dict[str, Any]] = []
        for pos in missing_positions:
            recs = self.catalog_repo.filter_products(
                category_slug=_POS_TO_SLUG.get(pos, pos), occasion=occasion, limit=3
            ) or self.catalog_repo.filter_products(category_slug=_POS_TO_SLUG.get(pos, pos), limit=3)
            for p in recs:
                purchase_suggestions.append({
                    "position": pos,
                    "source": "catalog",
                    "product_id": p.id,
                    "product_title": p.title,
                    "brand_name": p.brand.brand_name if p.brand else "CONFIT",
                    "color_family": p.color_family,
                    "dominant_hex": p.dominant_hex,
                    "image_url": p.thumbnail_url,
                    "price": to_float(p.base_price),
                })

        return {
            "occasion": occasion,
            "owned_items": owned_picks,
            "owned_count": len(owned_picks),
            "missing_positions": missing_positions,
            "purchase_suggestions": purchase_suggestions,
            "compatibility_score": comp.get("compatibility_score", 0),
            "is_complete_outfit": comp.get("is_complete_outfit", False),
            "wardrobe_first": True,
            "message": (
                "Built from pieces you already own — only the missing pieces are suggested for purchase."
                if owned_picks else
                "Your wardrobe has no ready items yet — upload pieces to unlock wardrobe-first styling."
            ),
        }

    def _format_outfit(self, o: Outfit) -> Dict[str, Any]:
        items_data = []
        # Render in canonical layer order. Legacy rows written before OUTFIT-02
        # carry arrival-index sort_order values; ordering by (sort_order, id)
        # keeps them deterministic instead of relying on DB row order.
        ordered = sorted(o.items, key=lambda it: (it.sort_order or 0, it.id))
        for it in ordered:
            price_val = to_float(it.product.base_price) if it.product and it.product.base_price is not None else 0.0
            items_data.append({
                "id": it.id,
                "product_id": it.product_id,
                "product_title": it.product.title if it.product else "Garment",
                "brand_name": it.product.brand.brand_name if it.product and it.product.brand else "CONFIT",
                "category_name": it.product.category.name if it.product and it.product.category else "Fashion",
                "price": price_val,
                "image_url": it.product.thumbnail_url if it.product else "",
                "color_hex": it.product.dominant_hex if it.product else "#1B1F3B",
                "position": it.position,
                "sku_id": it.product_sku_id,
                "selected_size": it.sku.size if it.sku else "M"
            })
        verdict = evaluate_composition(
            [{"position": i["position"], "product_sku_id": i.get("sku_id")} for i in items_data]
        )
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
            "created_at": o.created_at,
            "updated_at": getattr(o, "updated_at", None) or o.created_at,
            # Honest composition truth — the UI must not imply "Complete Look"
            # for a top-and-shoes pairing (audit finding: fabricated status).
            "is_complete": verdict.is_valid and not verdict.missing_positions,
            "completeness_status": completeness_status(items_data),
            "completeness_label": (
                "Complete Look"
                if completeness_status(items_data) == "complete_look"
                else "Partial Look"
            ),
            "missing_slots": list(verdict.missing_positions),
            "composition_warnings": list(verdict.warnings),
            # Sharing state is reported, never implied. If no live token
            # exists, is_shared is False and no URL is fabricated.
            "is_shared": self._is_share_live(o),
            "share_url": f"/looks/{o.share_token}" if self._is_share_live(o) else None,
            "share_expires_at": getattr(o, "share_expires_at", None) if self._is_share_live(o) else None,
            "share_view_count": int(getattr(o, "share_view_count", 0) or 0),
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
