"""Commerce domain: cart, pricing, checkout, payments, fulfillment, returns.

Server-authoritative totals. Client-submitted prices/discounts/taxes are ignored.
"""
from __future__ import annotations

import json
import os
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from decimal import Decimal, ROUND_HALF_UP
from backend.app.core.config import settings
from backend.app.core.money import (
    to_decimal,
    quantize_money,
    money_add,
    money_sub,
    money_mul,
    money_percent,
    money_min,
    money_max,
    money_sum,
    to_float,
)
from backend.app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    InventoryUnavailableError,
    InvalidStateTransitionError,
    PaymentFailedError,
    PromoIneligibleError,
    ResourceNotFoundError,
    ReturnIneligibleError,
    ValidationDomainError,
)
from backend.app.core.logging import logger
from backend.app.models.commerce import Cart, Order, OrderItem, PaymentTransaction
from backend.app.models.catalog import ProductSKU
from backend.app.providers.bnpl_provider import BNPLProvider
from backend.app.providers.payment.orchestrator import PaymentOrchestrator
from backend.app.repositories.catalog_repository import CatalogRepository
from backend.app.repositories.commerce_repository import CommerceRepository
from backend.app.repositories.profile_repository import ProfileRepository
from backend.app.services.no_photo_fit_service import NoPhotoFitService
from backend.app.services.product_context_service import ProductContextService


ORDER_TRANSITIONS: Dict[str, Set[str]] = {
    "placed": {"processing", "payment_pending", "cancelled", "failed", "return_requested", "exchange_requested"},
    "payment_pending": {"placed", "processing", "failed", "cancelled", "return_requested"},
    "processing": {
        "preparing",
        "ready_for_pickup",
        "dispatched",
        "shipped",
        "cancelled",
        "return_requested",
        "exchange_requested",
    },
    "preparing": {"ready_for_pickup", "dispatched", "cancelled", "return_requested", "exchange_requested"},
    "ready_for_pickup": {"picked_up", "cancelled", "return_requested", "exchange_requested"},
    "dispatched": {"out_for_delivery", "delivered", "cancelled", "return_requested", "exchange_requested"},
    "shipped": {"out_for_delivery", "delivered", "cancelled", "return_requested", "exchange_requested"},
    "out_for_delivery": {"delivered", "failed_delivery", "return_requested"},
    "delivered": {"return_requested", "exchange_requested", "completed"},
    "picked_up": {"return_requested", "exchange_requested", "completed"},
    "return_requested": {"partially_returned", "returned", "rejected"},
    "partially_returned": {"returned", "refund_pending"},
    "returned": {"refund_pending", "refunded"},
    "refund_pending": {"refunded", "refund_failed"},
    "refunded": {"completed"},
    "exchange_requested": {"processing", "cancelled"},
    "cancelled": set(),
    "completed": set(),
    "failed": {"cancelled", "payment_pending"},
    "rejected": set(),
    "refund_failed": {"refund_pending"},
    "failed_delivery": {"out_for_delivery", "cancelled", "returned"},
}

ALLOWED_RETURN_REASONS = {
    "Wrong Size",
    "Color Difference",
    "Changed Mind",
    "Style Mismatch",
    "Quality Issue",
}


class CommerceService:
    def __init__(self, db: Session):
        self.db = db
        self.commerce_repo = CommerceRepository(db)
        self.catalog_repo = CatalogRepository(db)
        self.bnpl_provider = BNPLProvider()
        self.payments = PaymentOrchestrator()
        self.fit_service = NoPhotoFitService(db)
        self.profile_repo = ProfileRepository(db)
        self.product_context = ProductContextService(db)

    # ------------------------------------------------------------------ cart
    def get_cart(self, session_token: str, user_id: Optional[int] = None) -> Dict[str, Any]:
        cart = self.commerce_repo.get_or_create_cart(session_token, user_id)
        cart_full = self.commerce_repo.get_cart_with_items(cart.id)
        return self._format_cart(cart_full or cart, user_id=user_id)

    def add_to_cart(
        self,
        session_token: str,
        product_sku_id: int,
        quantity: int = 1,
        user_id: Optional[int] = None,
        outfit_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        sku = self.catalog_repo.get_sku_by_id(product_sku_id)
        if not sku or not sku.is_in_stock or sku.stock_level < quantity:
            available = sku.stock_level if sku else 0
            raise InventoryUnavailableError(
                sku.sku_code if sku else str(product_sku_id), quantity, available
            )

        cart = self.commerce_repo.get_or_create_cart(session_token, user_id)
        cart_loaded = self.commerce_repo.get_cart_with_items(cart.id) or cart
        existing = next(
            (it for it in (cart_loaded.items or []) if it.product_sku_id == product_sku_id),
            None,
        )
        new_qty = quantity + (existing.quantity if existing else 0)
        if sku.stock_level < new_qty:
            raise InventoryUnavailableError(sku.sku_code, new_qty, sku.stock_level)

        self.commerce_repo.add_to_cart(cart.id, product_sku_id, quantity, outfit_id)
        logger.info("cart_item_added", cart_id=cart.id, sku_id=product_sku_id, quantity=quantity)
        cart_full = self.commerce_repo.get_cart_with_items(cart.id)
        return self._format_cart(cart_full or cart, user_id=user_id)

    def update_quantity(
        self,
        session_token: str,
        cart_item_id: int,
        quantity: int,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        cart = self.commerce_repo.get_or_create_cart(session_token, user_id)
        item = self.commerce_repo.get_cart_item_for_cart(cart.id, cart_item_id)
        if not item:
            raise ResourceNotFoundError("CartItem", cart_item_id)
        if quantity > 0:
            sku = item.sku
            if sku and sku.stock_level < quantity:
                raise InventoryUnavailableError(sku.sku_code, quantity, sku.stock_level)
        self.commerce_repo.update_cart_item_quantity(item.id, quantity)
        cart_full = self.commerce_repo.get_cart_with_items(cart.id)
        return self._format_cart(cart_full or cart, user_id=user_id)

    def remove_item(
        self, session_token: str, cart_item_id: int, user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        cart = self.commerce_repo.get_or_create_cart(session_token, user_id)
        item = self.commerce_repo.get_cart_item_for_cart(cart.id, cart_item_id)
        if not item:
            raise ResourceNotFoundError("CartItem", cart_item_id)
        self.commerce_repo.remove_cart_item(item.id)
        cart_full = self.commerce_repo.get_cart_with_items(cart.id)
        return self._format_cart(cart_full or cart, user_id=user_id)

    def merge_guest_cart(self, guest_token: str, user_id: int) -> Dict[str, Any]:
        cart = self.commerce_repo.merge_guest_into_user_cart(guest_token, user_id)
        logger.info("cart_merged", user_id=user_id)
        return self._format_cart(cart, user_id=user_id)

    def apply_promo(
        self, session_token: str, promo_code: Optional[str], user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        cart = self.commerce_repo.get_or_create_cart(session_token, user_id)
        cart_full = self.commerce_repo.get_cart_with_items(cart.id)
        if promo_code:
            subtotal, _, _ = self._line_items_from_cart(cart_full)
            self._resolve_promo(promo_code, subtotal, cart_full, user_id)
        self.commerce_repo.set_cart_promo(cart.id, (promo_code or "").upper().strip() or None)
        cart_full = self.commerce_repo.get_cart_with_items(cart.id)
        return self._format_cart(cart_full or cart, user_id=user_id)

    # -------------------------------------------------------------- checkout
    async def checkout(
        self,
        session_token: str,
        checkout_data: Dict[str, Any],
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        guest_email = (checkout_data.get("guest_email") or "").strip() or None
        if user_id is None and not guest_email:
            raise AuthenticationError(
                "Sign in or provide guest_email to complete checkout."
            )

        idempotency_key = checkout_data.get("idempotency_key")
        if idempotency_key:
            existing = self.commerce_repo.get_order_by_idempotency(idempotency_key)
            if existing:
                return self.get_order(existing.order_number)

        cart = self.commerce_repo.get_or_create_cart(session_token, user_id)
        cart_full = self.commerce_repo.get_cart_with_items(cart.id)
        if not cart_full or not cart_full.items:
            raise ValidationDomainError("Cannot checkout an empty cart.")

        self._assert_sizes_selected(cart_full)

        fulfillment = checkout_data.get("fulfillment_type", "delivery")
        if fulfillment not in ("delivery", "bopis"):
            raise ValidationDomainError("fulfillment_type must be 'delivery' or 'bopis'.")
        shipping_method = checkout_data.get("shipping_method") or "standard"
        if shipping_method not in ("standard", "express"):
            raise ValidationDomainError("shipping_method must be 'standard' or 'express'.")

        bopis_store_id = checkout_data.get("bopis_store_id")
        if fulfillment == "bopis" and not bopis_store_id:
            raise ValidationDomainError("bopis_store_id is required for boutique pickup.")
        if fulfillment == "delivery" and not checkout_data.get("address_line"):
            raise ValidationDomainError("A shipping address is required for home delivery.")

        payment_method = checkout_data.get("payment_method", "card")
        country = checkout_data.get("country") or settings.MARKET or "AE"

        subtotal, order_items_payload, brand_ids = self._line_items_from_cart(cart_full)
        promo_code = checkout_data.get("promo_code") or cart_full.promo_code
        discount, promo = (Decimal("0.00"), None)
        if promo_code:
            discount, promo = self._resolve_promo(promo_code, subtotal, cart_full, user_id)

        # Precise Decimal arithmetic for financial integrity
        free_threshold = to_decimal(settings.FREE_SHIPPING_THRESHOLD)
        express_fee = to_decimal(settings.EXPRESS_SHIPPING_FEE)
        standard_fee = to_decimal(settings.STANDARD_SHIPPING_FEE)
        tax_rate = to_decimal(settings.TAX_RATE)

        if fulfillment == "bopis":
            shipping = Decimal("0.00")
        elif shipping_method == "express":
            shipping = Decimal("0.00") if (subtotal - discount) >= free_threshold else express_fee
        else:
            shipping = Decimal("0.00") if (subtotal - discount) >= free_threshold else standard_fee

        taxable = money_max(subtotal - discount, Decimal("0.00"))
        tax = money_mul(taxable, tax_rate)
        total = money_max(taxable + tax + shipping, Decimal("0.00"))

        payments_live = bool(settings.PAYMENTS_LIVE)
        payment_mode = "live" if payments_live else "demo"
        installments = 4 if "bnpl" in payment_method else 1

        eta = datetime.now(timezone.utc) + timedelta(
            days=1 if fulfillment == "bopis" else (2 if shipping_method == "express" else 4)
        )

        # Inventory is reserved inside this transaction BEFORE payment capture.
        try:
            reservation_ids = self._reserve_inventory(
                order_items_payload,
                fulfillment_type=fulfillment,
                bopis_store_id=bopis_store_id,
            )
        except InventoryUnavailableError:
            self.db.rollback()
            raise

        try:
            order = self.commerce_repo.create_order(
                user_id=user_id,
                total_amount=total,
                subtotal_amount=subtotal,
                discount_amount=discount,
                tax_amount=tax,
                shipping_amount=shipping,
                currency="USD",
                payment_method=payment_method,
                payment_status="pending",
                payment_installments=installments,
                fulfillment_type=fulfillment,
                bopis_store_id=bopis_store_id,
                shipping_details={
                    "recipient_name": checkout_data.get("recipient_name"),
                    "address_line": checkout_data.get("address_line"),
                    "city": checkout_data.get("city"),
                    "country": country,
                    "phone": checkout_data.get("phone"),
                },
                idempotency_key=idempotency_key,
                try_on_assisted=bool(checkout_data.get("try_on_assisted", False)),
                stylist_assisted=bool(checkout_data.get("stylist_assisted", False)),
                items=order_items_payload,
                guest_email=guest_email,
                guest_session_token=session_token if user_id is None else None,
                promo_code=promo_code.upper().strip() if promo_code else None,
                payment_mode=payment_mode,
                shipping_method=shipping_method,
                estimated_delivery_date=eta,
            )
        except IntegrityError:
            self.db.rollback()
            if idempotency_key:
                existing = self.commerce_repo.get_order_by_idempotency(idempotency_key)
                if existing:
                    return self.get_order(existing.order_number)
            raise

        if promo:
            self.db.add(
                __import__("backend.app.models.commerce", fromlist=["PromotionRedemption"]).PromotionRedemption(
                    promotion_id=promo.id,
                    order_id=order.id,
                    user_id=user_id,
                    guest_email=guest_email,
                    discount_amount=discount,
                )
            )
            self.db.commit()

        self._attach_reservations(reservation_ids, order.id)

        # --- Real analytics instrumentation: purchase events with exclusive attribution ---
        # Fixed: product-level 30-day window using BrandAnalyticsEvent view events
        # Previously used any VisualSearchQuery existence + try_on_assisted flag, which could
        # incorrectly attribute unrelated purchases (different product, different brand, months ago)
        # Now: visual_search attribution only if user had a visual_search VIEW event for SAME product_id
        # within 30 days, preventing cross-product false attribution
        try:
            from backend.app.repositories.brand_repository import BrandRepository
            from backend.app.models.catalog_import import BrandAnalyticsEvent
            brand_repo = BrandRepository(self.db)
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)

            for item_payload in order_items_payload:
                brand_id = item_payload["brand_id"]
                product_id = item_payload["product_id"]
                sku_id = item_payload.get("product_sku_id")
                outfit_id = item_payload.get("outfit_id")
                subtotal_item = item_payload["subtotal"]

                # Priority: visual_search > outfit_builder > virtual_stylist > organic
                # Product-level 30-day attribution: check view event for same product + user within window
                has_product_visual_search = False
                if user_id and product_id:
                    try:
                        # Check for recent visual_search view event for this product and user
                        # Uses BrandAnalyticsEvent view events created by visual_search_service
                        # This ensures product identity lineage: query -> matches -> view event -> purchase
                        # Prevents attributing unrelated purchases when user searched for different product
                        existing_view = self.db.query(BrandAnalyticsEvent).filter(
                            BrandAnalyticsEvent.event_type == "view",
                            BrandAnalyticsEvent.attribution_source == "visual_search",
                            BrandAnalyticsEvent.product_id == product_id,
                            BrandAnalyticsEvent.user_id == user_id,
                            BrandAnalyticsEvent.created_at >= cutoff
                        ).first()
                        has_product_visual_search = existing_view is not None
                    except Exception as _vs_e:
                        logger.debug("visual_search_attribution_check_failed", product_id=product_id, error=str(_vs_e)[:100])
                        has_product_visual_search = False

                if has_product_visual_search:
                    attribution = "visual_search"
                elif outfit_id:
                    attribution = "outfit_builder"
                elif checkout_data.get("stylist_assisted"):
                    attribution = "virtual_stylist"
                else:
                    attribution = "organic"

                brand_repo.create_analytics_event(
                    brand_id=brand_id,
                    event_type="purchase",
                    attribution_source=attribution,
                    product_id=product_id,
                    sku_id=sku_id,
                    user_id=user_id,
                    session_token=session_token,
                    outfit_id=outfit_id,
                    order_id=order.id,
                    revenue_amount=subtotal_item,
                    event_metadata={"order_number": order.order_number, "payment_method": payment_method},
                    idempotency_key=f"purchase_{order.id}_{product_id}_{sku_id or 'na'}_{attribution}"
                )
        except Exception as _e:
            logger.warn("analytics_instrumentation_failed", order_id=order.id if 'order' in locals() else None, error=str(_e))

        try:
            self._notify(
                "order_created",
                order.order_number,
                guest_email or "",
                f"Order {order.order_number} created; payment {payment_method} pending confirmation.",
            )
        except Exception:
            logger.warn("commerce_notification_failed", order_number=order.order_number)

        pay_result = await self.payments.initiate_payment(
            method_id=payment_method,
            amount_minor=int((quantize_money(total) * Decimal("100")).to_integral_value(rounding=ROUND_HALF_UP)),
            currency_code="USD",
            customer_email=guest_email or "",
            order_number=order.order_number,
            country_code=country,
        )
        tx_status = pay_result.get("status") or "pending"
        mapped_payment_status = self._map_provider_status(tx_status, payment_method)
        self.commerce_repo.create_payment_transaction(
            order_id=order.id,
            provider=str(pay_result.get("provider") or payment_method),
            method=payment_method,
            provider_tx_id=str(pay_result.get("transaction_id") or uuid.uuid4().hex),
            amount=total,
            currency="USD",
            status=mapped_payment_status,
            mode=payment_mode,
            idempotency_key=f"pay:{idempotency_key or order.order_number}",
        )

        if mapped_payment_status in ("failed",):
            self._release_inventory_for_order(order)
            self._transition(order, "failed")
            order.payment_status = "failed"
            self.db.commit()
            raise PaymentFailedError(str(pay_result.get("provider")), "provider declined the payment")

        order.payment_status = mapped_payment_status
        if mapped_payment_status != "failed":
            self._commit_reservations(reservation_ids, order.id)
            try:
                self._notify(
                    "payment_recorded",
                    order.order_number,
                    guest_email or "",
                    f"Payment {mapped_payment_status} via {payment_method} ({payment_mode}).",
                )
            except Exception:
                logger.warn("commerce_notification_failed", order_number=order.order_number)
            next_status = "payment_pending" if mapped_payment_status == "pending" else "processing"
            if order.status != next_status:
                self._transition(order, next_status)
            self.commerce_repo.add_order_event(
                order.id,
                "payment_" + mapped_payment_status,
                "Payment recorded",
                (
                    f"Payment {mapped_payment_status} via {payment_method}"
                    + (" (demo adapter — not a live charge)" if payment_mode == "demo" else "")
                ),
            )
        self.db.commit()

        self.commerce_repo.clear_cart(cart.id)
        logger.info(
            "order_created",
            order_number=order.order_number,
            payment_status=order.payment_status,
            payment_mode=payment_mode,
            fulfillment=fulfillment,
        )
        return self.get_order(order.order_number)

    # ---------------------------------------------------------------- orders
    def get_order(self, order_number: str) -> Dict[str, Any]:
        order = self.commerce_repo.get_order_by_number(order_number)
        if not order:
            raise ResourceNotFoundError("Order", order_number)

        items_out = []
        outfit_groups: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for it in order.items:
            row = {
                "id": it.id,
                "product_id": it.product_id,
                "product_title": it.product_title,
                "brand_name": it.brand_name,
                "size": it.size,
                "color": it.color,
                "unit_price": it.unit_price,
                "quantity": it.quantity,
                "subtotal": it.subtotal,
                "is_returned": it.is_returned,
                "outfit_id": it.outfit_id,
                "fulfillment_group_id": it.fulfillment_group_id,
            }
            items_out.append(row)
            if it.outfit_id:
                outfit_groups[it.outfit_id].append(row)

        groups_out = []
        for g in order.fulfillment_groups or []:
            groups_out.append(
                {
                    "id": g.id,
                    "brand_name": g.brand_name,
                    "fulfillment_type": g.fulfillment_type,
                    "status": g.status,
                    "carrier": g.carrier,
                    "tracking_number": g.tracking_number,
                }
            )

        return {
            "id": order.id,
            "order_number": order.order_number,
            "user_id": order.user_id,
            "guest_email": order.guest_email,
            "status": order.status,
            "total_amount": order.total_amount,
            "subtotal_amount": order.subtotal_amount,
            "discount_amount": order.discount_amount,
            "tax_amount": order.tax_amount,
            "shipping_amount": order.shipping_amount,
            "currency": order.currency,
            "promo_code": order.promo_code,
            "payment_method": order.payment_method,
            "payment_status": order.payment_status,
            "payment_installments": order.payment_installments,
            "payment_mode": order.payment_mode,
            "fulfillment_type": order.fulfillment_type,
            "shipping_method": order.shipping_method,
            "bopis_store_name": order.bopis_store.name if order.bopis_store else None,
            "bopis_pickup_code": order.bopis_pickup_code,
            "shipping_recipient_name": order.shipping_recipient_name,
            "shipping_address_line": order.shipping_address_line,
            "shipping_city": order.shipping_city,
            "tracking_number": order.tracking_number,
            "estimated_delivery_date": order.estimated_delivery_date,
            "try_on_assisted": order.try_on_assisted,
            "stylist_assisted": order.stylist_assisted,
            "items": items_out,
            "fulfillment_groups": groups_out,
            "outfit_groups": [
                {"outfit_id": oid, "items": rows} for oid, rows in outfit_groups.items()
            ],
            "created_at": order.created_at,
        }

    def assert_order_access(
        self, order: Dict[str, Any], user, session_token: Optional[str] = None
    ) -> None:
        from backend.app.models.user import UserRole

        if user and getattr(user, "role", None) == UserRole.ADMIN:
            return
        if user and order.get("user_id") == user.id:
            return
        if user and order.get("user_id") and order.get("user_id") != user.id:
            raise AuthorizationError("Access denied: You cannot view order details of another customer.")
        # Guest access: unguessable order number is the capability. Authenticated
        # cross-user access is already rejected above.
        if user is None:
            return

    def get_order_tracking(self, order_number: str) -> Dict[str, Any]:
        order = self.commerce_repo.get_order_by_number(order_number)
        if not order:
            raise ResourceNotFoundError("Order", order_number)

        is_bopis = order.fulfillment_type == "bopis"
        events = sorted(order.events or [], key=lambda e: e.created_at)
        event_keys = {e.status_key for e in events}

        if is_bopis:
            template = [
                ("placed", "Order Placed & Confirmed", "Payment recorded and routed to boutique."),
                ("processing", "Store Preparing Items", "Associate pulling garments and verifying quality."),
                ("ready_for_pickup", "Ready for Boutique Pickup", f"Present pickup code {order.bopis_pickup_code} at the desk."),
                ("picked_up", "Collected by Customer", "Pickup completed."),
            ]
        else:
            template = [
                ("placed", "Order Placed", "Order received."),
                ("processing", "Fulfillment & Quality Check", "Garments prepared for dispatch."),
                ("dispatched", "Dispatched with Carrier", "In transit."),
                ("out_for_delivery", "Out for Delivery", "Courier on route."),
                ("delivered", "Delivered", "Handed to recipient."),
            ]

        status_rank = [t[0] for t in template]
        current = order.status
        if current == "picked_up":
            current_idx = status_rank.index("picked_up") if "picked_up" in status_rank else len(status_rank) - 1
        elif current in status_rank:
            current_idx = status_rank.index(current)
        else:
            current_idx = 0

        timeline = []
        for idx, (key, title, desc) in enumerate(template):
            matching_event = next((e for e in events if e.status_key == key or e.status_key.endswith(key)), None)
            is_completed = idx < current_idx or current == key and idx <= current_idx and current in (
                "delivered",
                "picked_up",
                "completed",
            )
            if current in status_rank and idx < current_idx:
                is_completed = True
            is_current = key == current or (idx == current_idx)
            timeline.append(
                {
                    "status_key": key,
                    "title": title,
                    "description": desc,
                    "timestamp": matching_event.created_at if matching_event else (
                        order.created_at if is_completed and idx == 0 else None
                    ),
                    "is_completed": is_completed,
                    "is_current": is_current and not is_completed,
                }
            )
            if is_current and is_completed:
                timeline[-1]["is_current"] = False

        # Ensure exactly one current marker when the order is still in flight.
        if not any(m["is_current"] for m in timeline) and current not in ("delivered", "picked_up", "completed", "cancelled"):
            for m in timeline:
                if m["status_key"] == current:
                    m["is_current"] = True
                    break
            else:
                timeline[min(current_idx, len(timeline) - 1)]["is_current"] = True

        store_info = None
        if order.bopis_store:
            store_info = {
                "name": order.bopis_store.name,
                "address": order.bopis_store.address,
                "city": order.bopis_store.city,
                "pickup_instructions": order.bopis_store.pickup_instructions
                or "Visit Customer Service desk with your digital pickup code.",
                "pickup_code": order.bopis_pickup_code,
            }

        shipments = []
        for g in order.fulfillment_groups or []:
            shipments.append(
                {
                    "brand_name": g.brand_name,
                    "status": g.status,
                    "carrier": g.carrier,
                    "tracking_number": g.tracking_number,
                    "fulfillment_type": g.fulfillment_type,
                }
            )

        return {
            "order_number": order.order_number,
            "current_status": order.status,
            "estimated_delivery": (
                order.estimated_delivery_date.date().isoformat()
                if order.estimated_delivery_date
                else None
            ),
            "carrier": next(
                (g.carrier for g in (order.fulfillment_groups or []) if g.carrier),
                None,
            ),
            "tracking_number": order.tracking_number,
            "timeline": timeline,
            "bopis_store_info": store_info,
            "shipments": shipments,
        }

    def transition_order(self, order_number: str, new_status: str) -> Dict[str, Any]:
        order = self.commerce_repo.get_order_by_number(order_number)
        if not order:
            raise ResourceNotFoundError("Order", order_number)
        self._transition(order, new_status)
        self.commerce_repo.add_order_event(
            order.id, new_status, f"Status → {new_status}", f"Order moved to {new_status}."
        )
        return self.get_order(order.order_number)

    # --------------------------------------------------------------- returns
    def create_return(
        self,
        user_id: Optional[int],
        order_id: int,
        reason: str,
        details: Optional[str],
        item_ids: List[int],
        guest_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        order = self.commerce_repo.get_order_by_id(order_id)
        if not order:
            raise ResourceNotFoundError("Order", order_id)
        if user_id and order.user_id and order.user_id != user_id:
            raise AuthorizationError("You cannot return another customer's order.")
        if user_id is None and guest_email and order.guest_email and order.guest_email.lower() != guest_email.lower():
            raise AuthorizationError("Guest email does not match this order.")

        if reason not in ALLOWED_RETURN_REASONS:
            raise ValidationDomainError(f"Unsupported return reason: {reason}")
        if not item_ids:
            raise ValidationDomainError("Select at least one item to return.")

        eligible_statuses = {
            "delivered",
            "picked_up",
            "completed",
        }
        if order.status not in eligible_statuses:
            raise ReturnIneligibleError(f"Order status '{order.status}' is not eligible for return.")

        window = timedelta(days=settings.RETURN_WINDOW_DAYS)
        if order.created_at.replace(tzinfo=timezone.utc) + window < datetime.now(timezone.utc):
            raise ReturnIneligibleError(
                f"The {settings.RETURN_WINDOW_DAYS}-day return window has closed."
            )

        owned_ids = {it.id for it in order.items}
        unknown = [i for i in item_ids if i not in owned_ids]
        if unknown:
            raise ValidationDomainError("One or more items do not belong to this order.")
        already = [it for it in order.items if it.id in item_ids and it.is_returned]
        if already:
            raise ReturnIneligibleError("One or more items have already been returned.")

        refund_subtotal = money_sum([it.subtotal for it in order.items if it.id in item_ids])
        label_url, label_ref = self._generate_return_label(order)

        req = self.commerce_repo.create_return_request(
            order_id=order.id,
            user_id=user_id or order.user_id,
            reason=reason,
            details=details,
            refund_amount=refund_subtotal,
            item_ids=item_ids,
            try_on_used=order.try_on_assisted,
            return_label_url=label_url,
            label_provider_ref=label_ref,
            guest_email=guest_email or order.guest_email,
        )
        self._transition(order, "return_requested")
        self.commerce_repo.add_order_event(
            order.id, "return_requested", "Return requested", f"Return {req.return_number} opened."
        )
        logger.info("return_created", return_number=req.return_number, order_id=order.id)
        self._notify(
            "return_requested",
            order.order_number,
            guest_email or order.guest_email or "",
            f"Return {req.return_number} opened for order {order.order_number}.",
        )
        return self._format_return(req)

    def get_return(self, return_id: int, user_id: int) -> Dict[str, Any]:
        req = self.commerce_repo.get_return_by_id(return_id)
        if not req:
            raise ResourceNotFoundError("ReturnRequest", return_id)
        if req.user_id and req.user_id != user_id:
            raise AuthorizationError("You cannot view another customer's return.")
        return self._format_return(req)

    async def create_exchange(
        self,
        user_id: int,
        order_id: int,
        original_item_id: int,
        replacement_sku_id: int,
    ) -> Dict[str, Any]:
        order = self.commerce_repo.get_order_by_id(order_id)
        if not order or order.user_id != user_id:
            raise ResourceNotFoundError("Order", order_id)
        item = next((it for it in order.items if it.id == original_item_id), None)
        if not item:
            raise ResourceNotFoundError("OrderItem", original_item_id)
        if item.is_returned:
            raise ReturnIneligibleError("Returned items cannot be exchanged.")

        sku = self.catalog_repo.get_sku_by_id(replacement_sku_id)
        if not sku or not sku.is_in_stock or sku.stock_level < 1:
            raise InventoryUnavailableError(
                sku.sku_code if sku else str(replacement_sku_id), 1, sku.stock_level if sku else 0
            )
        if sku.product_id != item.product_id:
            raise ValidationDomainError("Exchange replacement must be a variant of the same product.")

        new_price = to_decimal(sku.price_override or sku.product.base_price)
        unit_price_dec = to_decimal(item.unit_price)
        delta = money_sub(new_price, unit_price_dec)
        payment_status = "not_required"
        if delta > 0:
            payment_status = "delta_due"
        elif delta < 0:
            payment_status = "credit_due"

        self._reserve_inventory(
            [
                {
                    "product_sku_id": sku.id,
                    "quantity": 1,
                    "sku_code": sku.sku_code,
                }
            ],
            fulfillment_type=order.fulfillment_type,
            bopis_store_id=order.bopis_store_id,
        )
        req = self.commerce_repo.create_exchange(
            order_id=order.id,
            user_id=user_id,
            original_item_id=item.id,
            replacement_sku_id=sku.id,
            price_delta=delta,
            payment_status=payment_status,
        )
        self._transition(order, "exchange_requested")
        logger.info("exchange_created", exchange_number=req.exchange_number, price_delta=delta)
        return {
            "id": req.id,
            "exchange_number": req.exchange_number,
            "order_id": req.order_id,
            "original_item_id": req.original_item_id,
            "replacement_sku_id": req.replacement_sku_id,
            "price_delta": req.price_delta,
            "status": req.status,
            "payment_status": req.payment_status,
            "created_at": req.created_at,
        }

    async def process_webhook(self, provider: str, payload: Dict[str, Any], raw_body: bytes, signature: str) -> Dict[str, Any]:
        if not self.payments.verify_webhook(provider, raw_body, signature or ""):
            from fastapi import HTTPException

            raise HTTPException(status_code=401, detail="Invalid webhook signature")

        event_id = str(payload.get("id") or payload.get("event_id") or payload.get("eventId") or "")
        if not event_id:
            raise ValidationDomainError("Webhook payload is missing an event id.")
        existing = self.commerce_repo.get_webhook_event(provider, event_id)
        if existing:
            return {"status": "duplicate", "provider": provider, "event_id": event_id}

        order_number = payload.get("order_number") or (payload.get("data") or {}).get("order_number")
        event_type = payload.get("event") or payload.get("type") or ""
        self.commerce_repo.record_webhook_event(provider, event_id, order_number)

        if order_number:
            order = self.commerce_repo.get_order_by_number(order_number)
            if order:
                if event_type in ("payment.captured", "charge.succeeded", "payment_intent.succeeded"):
                    order.payment_status = "paid"
                    if order.status in ("placed", "payment_pending"):
                        self._transition(order, "processing")
                    self.commerce_repo.add_order_event(
                        order.id, "paid", "Payment captured", "Provider confirmed capture."
                    )
                elif event_type in ("payment.failed", "charge.failed"):
                    order.payment_status = "failed"
                    self._release_inventory_for_order(order)
                    self._transition(order, "failed")
                elif event_type in ("refund.succeeded", "charge.refunded"):
                    order.payment_status = "refunded"
                    self._transition(order, "refunded")
                self.db.commit()

        logger.info("webhook_processed", provider=provider, event_id=event_id, webhook_event=event_type)
        return {"status": "received", "provider": provider, "verified": True, "event": event_type}

    async def refund_return(self, return_id: int) -> Dict[str, Any]:
        req = self.commerce_repo.get_return_by_id(return_id)
        if not req:
            raise ResourceNotFoundError("ReturnRequest", return_id)
        order = req.order
        tx = (
            self.db.query(PaymentTransaction)
            .filter(PaymentTransaction.order_id == order.id)
            .order_by(PaymentTransaction.created_at.desc())
            .first()
        )
        if not tx:
            raise ValidationDomainError("No payment transaction exists to refund.")
        result = await self.payments.refund(
            provider_tx_id=tx.provider_tx_id,
            amount=req.refund_amount,
            method=order.payment_method,
            mode=order.payment_mode,
        )
        if result.get("status") not in ("refunded", "refund_pending"):
            raise PaymentFailedError(tx.provider, "refund was not confirmed")
        # Precise Decimal handling for refunds
        current_refunded = to_decimal(tx.refunded_amount)
        refund_req = to_decimal(req.refund_amount)
        tx.refunded_amount = money_add(current_refunded, refund_req)
        tx.status = result["status"]
        req.status = "refunded" if result["status"] == "refunded" else "approved"
        if result["status"] == "refunded":
            total_dec = to_decimal(order.total_amount)
            refunded_dec = to_decimal(tx.refunded_amount)
            # Allow 0.01 tolerance for rounding, but use Decimal
            tolerance = Decimal("0.01")
            order.payment_status = "refunded" if refunded_dec >= (total_dec - tolerance) else order.payment_status
            self._transition(order, "refunded" if refunded_dec >= (total_dec - tolerance) else "partially_returned")
        self.db.commit()
        return self._format_return(req)

    # -------------------------------------------------------------- internals
    def _line_items_from_cart(self, cart: Cart) -> Tuple[Decimal, List[Dict[str, Any]], Set[int]]:
        subtotal = Decimal("0.00")
        payload = []
        brands: Set[int] = set()
        for it in cart.items:
            sku = it.sku
            prod = sku.product
            unit_price = to_decimal(sku.price_override if sku.price_override is not None else prod.base_price)
            line_sub = money_mul(unit_price, it.quantity)
            subtotal = money_add(subtotal, line_sub)
            brands.add(prod.brand_id)
            payload.append(
                {
                    "product_sku_id": sku.id,
                    "sku_code": sku.sku_code,
                    "product_id": prod.id,
                    "brand_id": prod.brand_id,
                    "product_title": prod.title,
                    "brand_name": prod.brand.brand_name if prod.brand else "CONFIT",
                    "size": sku.size,
                    "color": sku.color,
                    "unit_price": unit_price,  # Decimal exact
                    "quantity": it.quantity,
                    "subtotal": line_sub,  # Decimal exact
                    "outfit_id": it.outfit_id,
                }
            )
        return subtotal, payload, brands

    def _assert_sizes_selected(self, cart: Cart) -> None:
        for it in cart.items:
            sku = it.sku
            if not sku or not sku.size:
                raise ValidationDomainError("Every cart item must have a selected size.")
            if not sku.is_in_stock:
                raise InventoryUnavailableError(sku.sku_code, it.quantity, 0)

    def _resolve_promo(self, code: str, subtotal: Decimal, cart: Cart, user_id: Optional[int]):
        promo = self.commerce_repo.get_promotion_by_code(code)
        now = datetime.now(timezone.utc)
        if not promo or not promo.is_active:
            raise PromoIneligibleError(code, "code is not recognised or inactive")
        if promo.starts_at and promo.starts_at.replace(tzinfo=timezone.utc) > now:
            raise PromoIneligibleError(code, "code is not yet active")
        if promo.expires_at and promo.expires_at.replace(tzinfo=timezone.utc) < now:
            raise PromoIneligibleError(code, "code has expired")
        min_order = to_decimal(promo.min_order_amount)
        if subtotal < min_order:
            raise PromoIneligibleError(code, f"minimum order is {promo.min_order_amount}")
        if promo.max_redemptions is not None:
            used = self.commerce_repo.count_redemptions(promo.id)
            if used >= promo.max_redemptions:
                raise PromoIneligibleError(code, "redemption limit reached")
        if user_id and promo.max_per_user:
            used_user = self.commerce_repo.count_redemptions(promo.id, user_id=user_id)
            if used_user >= promo.max_per_user:
                raise PromoIneligibleError(code, "you have already used this code")

        eligible_subtotal = Decimal("0.00")
        for it in cart.items:
            prod = it.sku.product
            if promo.brand_id and prod.brand_id != promo.brand_id:
                continue
            if promo.product_id and prod.id != promo.product_id:
                continue
            unit = to_decimal(it.sku.price_override if it.sku.price_override is not None else prod.base_price)
            eligible_subtotal = money_add(eligible_subtotal, money_mul(unit, it.quantity))
        if eligible_subtotal <= Decimal("0.00"):
            raise PromoIneligibleError(code, "no items in the cart qualify")

        discount_val = to_decimal(promo.discount_value)
        if promo.discount_type == "percent":
            discount = money_percent(eligible_subtotal, discount_val)
        else:
            discount = money_min(discount_val, eligible_subtotal)
        return discount, promo

    def _reserve_inventory(
        self,
        items: List[Dict[str, Any]],
        fulfillment_type: str,
        bopis_store_id: Optional[int],
    ) -> List[int]:
        """
        Atomic inventory reservation - Phase 1: validate all, Phase 2: modify.
        Previously deducted global stock before checking store inventory, relying on rollback.
        Now checks BOTH global and store availability first, then modifies - cleaner and safer.
        """
        from backend.app.models.commerce import InventoryReservation

        # Phase 1: Lock and validate ALL items before any modification
        locked_data: List[Dict[str, Any]] = []
        for item in items:
            sku = self.commerce_repo.lock_sku(item["product_sku_id"])
            if not sku or sku.stock_level < item["quantity"] or not sku.is_in_stock:
                raise InventoryUnavailableError(
                    item.get("sku_code") or str(item["product_sku_id"]),
                    item["quantity"],
                    sku.stock_level if sku else 0,
                )

            store_inv = None
            if fulfillment_type == "bopis" and bopis_store_id:
                store_inv = self.commerce_repo.lock_store_inventory(bopis_store_id, sku.id)
                available = (store_inv.quantity - store_inv.reserved_quantity) if store_inv else 0
                if not store_inv or available < item["quantity"]:
                    raise InventoryUnavailableError(
                        sku.sku_code, item["quantity"], available
                    )

            locked_data.append({
                "sku": sku,
                "store_inv": store_inv,
                "quantity": item["quantity"],
                "sku_code": item.get("sku_code") or sku.sku_code,
            })

        # Phase 2: All validations passed - now modify atomically
        held: List[InventoryReservation] = []
        for data in locked_data:
            sku = data["sku"]
            store_inv = data["store_inv"]
            qty = data["quantity"]

            sku.stock_level -= qty
            if sku.stock_level <= 0:
                sku.is_in_stock = False
                sku.stock_level = 0

            if store_inv:
                store_inv.reserved_quantity += qty

            row = InventoryReservation(
                sku_id=sku.id,
                quantity=qty,
                store_id=bopis_store_id if fulfillment_type == "bopis" else None,
                status="held",
            )
            self.db.add(row)
            held.append(row)

        self.db.flush()
        return [row.id for row in held if row.id is not None]

    def _attach_reservations(self, reservation_ids: List[int], order_id: int) -> None:
        from backend.app.models.commerce import InventoryReservation

        if not reservation_ids:
            return
        rows = (
            self.db.query(InventoryReservation)
            .filter(InventoryReservation.id.in_(reservation_ids))
            .all()
        )
        for row in rows:
            row.order_id = order_id
        self.db.commit()

    def _commit_reservations(self, reservation_ids: List[int], order_id: int) -> None:
        from backend.app.models.commerce import InventoryReservation

        if not reservation_ids:
            return
        rows = (
            self.db.query(InventoryReservation)
            .filter(InventoryReservation.id.in_(reservation_ids))
            .all()
        )
        for row in rows:
            row.order_id = order_id
            row.status = "committed"

    def _release_inventory_for_order(self, order: Order) -> None:
        from backend.app.models.commerce import InventoryReservation

        rows = (
            self.db.query(InventoryReservation)
            .filter(InventoryReservation.order_id == order.id, InventoryReservation.status != "released")
            .all()
        )
        for row in rows:
            sku = self.commerce_repo.lock_sku(row.sku_id)
            if sku:
                sku.stock_level += row.quantity
                sku.is_in_stock = True
            if row.store_id:
                inv = self.commerce_repo.lock_store_inventory(row.store_id, row.sku_id)
                if inv:
                    inv.reserved_quantity = max(0, inv.reserved_quantity - row.quantity)
            row.status = "released"
            row.released_at = datetime.now(timezone.utc)

    def _transition(self, order: Order, new_status: str) -> None:
        allowed = ORDER_TRANSITIONS.get(order.status, set())
        if new_status == order.status:
            return
        if new_status not in allowed:
            raise InvalidStateTransitionError(order.status, new_status)
        order.status = new_status
        if new_status == "ready_for_pickup":
            order.ready_for_pickup_at = datetime.now(timezone.utc)
        self.db.flush()

    def _map_provider_status(self, status: str, method: str) -> str:
        if status in ("captured", "succeeded", "paid"):
            return "paid"
        if status in ("authorized",):
            return "authorized"
        if status in ("pending_delivery",) or method == "cod":
            return "pending"
        if status in ("failed", "declined"):
            return "failed"
        return "pending"

    def _generate_return_label(self, order: Order) -> Tuple[Optional[str], Optional[str]]:
        """Persist a real return-authorisation document. Not a carrier label
        unless a shipping provider is configured — we never invent a DHL URL.
        """
        ref = f"RA-{uuid.uuid4().hex[:10].upper()}"
        directory = os.path.join(settings.STORAGE_LOCAL_DIR, "return-labels")
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, f"{ref}.txt")
        body = (
            f"CONFIT Return Authorisation\n"
            f"Reference: {ref}\n"
            f"Order: {order.order_number}\n"
            f"Issued: {datetime.now(timezone.utc).isoformat()}\n"
            f"This is a platform return authorisation. A carrier label is issued "
            f"only when a shipping provider is configured.\n"
        )
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(body)
        return f"/api/v1/returns/labels/{ref}", ref

    def _format_return(self, req) -> Dict[str, Any]:
        return {
            "id": req.id,
            "return_number": req.return_number,
            "order_id": req.order_id,
            "status": req.status,
            "reason": req.reason,
            "refund_amount": req.refund_amount,
            "return_label_url": req.return_label_url or "",
            "created_at": req.created_at,
            "resolved_at": req.resolved_at,
        }

    def _fit_verdict_for_sku(self, sku: ProductSKU, user_id: Optional[int]) -> str:
        if not sku or not sku.size:
            return "Size required"
        if not sku.is_in_stock or sku.stock_level <= 0:
            return f"Size {sku.size} unavailable"
        if not user_id:
            return f"Size {sku.size} selected"
        profile = self.profile_repo.get_by_user_id(user_id)
        if not profile:
            return f"Size {sku.size} selected"
        preferred = profile.size_tops or profile.size_bottoms
        if preferred and preferred.upper() == sku.size.upper():
            return f"Size {sku.size} matches your profile"
        return f"Size {sku.size} selected"

    def _format_cart(self, cart: Cart, user_id: Optional[int] = None) -> Dict[str, Any]:
        items_out = []
        subtotal = Decimal("0.00")
        count = 0
        brands: Set[str] = set()
        outfit_groups: Dict[int, List[int]] = defaultdict(list)

        for it in cart.items if cart and cart.items else []:
            sku = it.sku
            prod = sku.product
            price = to_decimal(sku.price_override if sku.price_override is not None else prod.base_price)
            line_sub = money_mul(price, it.quantity)
            subtotal = money_add(subtotal, line_sub)
            count += it.quantity
            brand_name = prod.brand.brand_name if prod.brand else "CONFIT"
            brands.add(brand_name)
            if it.outfit_id:
                outfit_groups[it.outfit_id].append(it.id)
            items_out.append(
                {
                    "id": it.id,
                    "product_sku_id": sku.id,
                    "product_id": prod.id,
                    "product_title": prod.title,
                    "product_title_ar": prod.title_ar,
                    "brand_name": brand_name,
                    "size": sku.size,
                    "color": sku.color,
                    "unit_price": price,
                    "quantity": it.quantity,
                    "subtotal": line_sub,
                    "image_url": prod.thumbnail_url,
                    "ai_fit_verdict": self._fit_verdict_for_sku(sku, user_id),
                    "in_stock": bool(sku.is_in_stock and sku.stock_level >= it.quantity),
                    "outfit_id": it.outfit_id,
                }
            )

        discount = Decimal("0.00")
        promo_code = cart.promo_code if cart else None
        if promo_code and cart:
            try:
                discount, _ = self._resolve_promo(promo_code, subtotal, cart, user_id)
            except PromoIneligibleError:
                discount = Decimal("0.00")
                promo_code = None

        taxable = money_max(subtotal - discount, Decimal("0.00"))
        tax_rate = to_decimal(settings.TAX_RATE)
        tax = money_mul(taxable, tax_rate)
        free_threshold = to_decimal(settings.FREE_SHIPPING_THRESHOLD)
        standard_fee = to_decimal(settings.STANDARD_SHIPPING_FEE)
        shipping = Decimal("0.00") if (taxable >= free_threshold or subtotal == Decimal("0.00")) else standard_fee
        total = money_max(taxable + tax + shipping, Decimal("0.00"))

        quote = BNPLProvider(provider_name=settings.BNPL_DEFAULT_PROVIDER).quote_sync(
            amount=total, currency="USD"
        )

        return {
            "id": cart.id if cart else 0,
            "items": items_out,
            "subtotal": subtotal,
            "discount_amount": discount,
            "tax_amount": tax,
            "shipping_amount": shipping,
            "total": total,
            "currency": "USD",
            "items_count": count,
            "bnpl_monthly_quote": quote.get("installment_amount") or 0.0,
            "promo_code": promo_code,
            "brands": sorted(brands),
            "fit_summary": [
                {
                    "cart_item_id": it["id"],
                    "title": it["product_title"],
                    "size": it["size"],
                    "verdict": it["ai_fit_verdict"],
                    "size_confirmed": bool(it["size"] and it["in_stock"]),
                }
                for it in items_out
            ],
            "outfit_groups": [
                {"outfit_id": oid, "item_ids": ids} for oid, ids in outfit_groups.items()
            ],
        }

    def _notify(self, event: str, order_number: str, recipient: str, summary: str) -> None:
        """Order lifecycle notice. Uses the existing logger + EMAIL_PROVIDER
        configuration; never fabricates a successful send when no provider is set.
        """
        logger.info(
            "commerce_notification",
            commerce_event=event,
            order_number=order_number,
            has_recipient=bool(recipient),
            email_provider_configured=bool(settings.EMAIL_PROVIDER),
            summary=summary,
        )
