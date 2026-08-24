from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.app.models.commerce import Cart, Order
from backend.app.repositories.commerce_repository import CommerceRepository
from backend.app.repositories.catalog_repository import CatalogRepository
from backend.app.providers.bnpl_provider import BNPLProvider
from backend.app.core.exceptions import ResourceNotFoundError, InventoryUnavailableError, ValidationDomainError


class CommerceService:
    def __init__(self, db: Session):
        self.db = db
        self.commerce_repo = CommerceRepository(db)
        self.catalog_repo = CatalogRepository(db)
        self.bnpl_provider = BNPLProvider()

    def get_cart(self, session_token: str, user_id: Optional[int] = None) -> Dict[str, Any]:
        cart = self.commerce_repo.get_or_create_cart(session_token, user_id)
        cart_full = self.commerce_repo.get_cart_with_items(cart.id)
        return self._format_cart(cart_full or cart)

    def add_to_cart(
        self,
        session_token: str,
        product_sku_id: int,
        quantity: int = 1,
        user_id: Optional[int] = None,
        outfit_id: Optional[int] = None
    ) -> Dict[str, Any]:
        sku = self.catalog_repo.get_sku_by_id(product_sku_id)
        if not sku or not sku.is_in_stock:
            raise InventoryUnavailableError(sku.sku_code if sku else str(product_sku_id), quantity, 0)

        cart = self.commerce_repo.get_or_create_cart(session_token, user_id)
        self.commerce_repo.add_to_cart(cart.id, product_sku_id, quantity, outfit_id)

        cart_full = self.commerce_repo.get_cart_with_items(cart.id)
        return self._format_cart(cart_full or cart)

    def update_quantity(self, session_token: str, cart_item_id: int, quantity: int, user_id: Optional[int] = None) -> Dict[str, Any]:
        cart = self.commerce_repo.get_or_create_cart(session_token, user_id)
        self.commerce_repo.update_cart_item_quantity(cart_item_id, quantity)
        cart_full = self.commerce_repo.get_cart_with_items(cart.id)
        return self._format_cart(cart_full or cart)

    def remove_item(self, session_token: str, cart_item_id: int, user_id: Optional[int] = None) -> Dict[str, Any]:
        cart = self.commerce_repo.get_or_create_cart(session_token, user_id)
        self.commerce_repo.remove_cart_item(cart_item_id)
        cart_full = self.commerce_repo.get_cart_with_items(cart.id)
        return self._format_cart(cart_full or cart)

    async def checkout(
        self,
        session_token: str,
        checkout_data: Dict[str, Any],
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        cart = self.commerce_repo.get_or_create_cart(session_token, user_id)
        cart_full = self.commerce_repo.get_cart_with_items(cart.id)
        if not cart_full or not cart_full.items:
            raise ValidationDomainError("Cannot checkout an empty cart.")

        # Check idempotency key if provided
        idempotency_key = checkout_data.get("idempotency_key")
        if idempotency_key:
            existing_order = self.db.query(Order).filter(Order.idempotency_key == idempotency_key).first()
            if existing_order:
                return self.get_order(existing_order.order_number)

        # Calculate totals
        subtotal = 0.0
        order_items_payload = []
        for it in cart_full.items:
            sku = it.sku
            prod = sku.product
            unit_price = sku.price_override or prod.base_price
            line_sub = unit_price * it.quantity
            subtotal += line_sub

            order_items_payload.append({
                "product_sku_id": sku.id,
                "product_id": prod.id,
                "brand_id": prod.brand_id,
                "product_title": prod.title,
                "brand_name": prod.brand.brand_name if prod.brand else "CONFIT",
                "size": sku.size,
                "color": sku.color,
                "unit_price": unit_price,
                "quantity": it.quantity,
                "subtotal": line_sub
            })

        discount = 20.0 if checkout_data.get("promo_code") in ["CONFIT10", "STYLE2026"] else 0.0
        tax = round((subtotal - discount) * 0.05, 2)
        fulfillment = checkout_data.get("fulfillment_type", "delivery")
        shipping = 0.0 if fulfillment == "bopis" else (15.0 if subtotal < 250 else 0.0)
        total = round(max(0.0, subtotal - discount + tax + shipping), 2)

        payment_method = checkout_data.get("payment_method", "card")
        installments = 4 if "bnpl" in payment_method else 1

        order = self.commerce_repo.create_order(
            user_id=user_id,
            total_amount=total,
            subtotal_amount=subtotal,
            discount_amount=discount,
            tax_amount=tax,
            shipping_amount=shipping,
            currency="USD",
            payment_method=payment_method,
            payment_status="paid" if payment_method != "cod" else "pending",
            payment_installments=installments,
            fulfillment_type=fulfillment,
            bopis_store_id=checkout_data.get("bopis_store_id"),
            shipping_details={
                "recipient_name": checkout_data.get("recipient_name"),
                "address_line": checkout_data.get("address_line"),
                "city": checkout_data.get("city"),
                "country": checkout_data.get("country", "UAE"),
                "phone": checkout_data.get("phone")
            },
            idempotency_key=idempotency_key,
            try_on_assisted=checkout_data.get("try_on_assisted", True),
            stylist_assisted=checkout_data.get("stylist_assisted", False),
            items=order_items_payload
        )

        # Clear cart on successful order creation
        self.commerce_repo.clear_cart(cart.id)

        return self.get_order(order.order_number)

    def get_order(self, order_number: str) -> Dict[str, Any]:
        order = self.commerce_repo.get_order_by_number(order_number)
        if not order:
            raise ResourceNotFoundError("Order", order_number)

        items_out = []
        for it in order.items:
            items_out.append({
                "id": it.id,
                "product_id": it.product_id,
                "product_title": it.product_title,
                "brand_name": it.brand_name,
                "size": it.size,
                "color": it.color,
                "unit_price": it.unit_price,
                "quantity": it.quantity,
                "subtotal": it.subtotal,
                "is_returned": it.is_returned
            })

        return {
            "id": order.id,
            "order_number": order.order_number,
            "status": order.status,
            "total_amount": order.total_amount,
            "subtotal_amount": order.subtotal_amount,
            "discount_amount": order.discount_amount,
            "tax_amount": order.tax_amount,
            "shipping_amount": order.shipping_amount,
            "currency": order.currency,
            "payment_method": order.payment_method,
            "payment_status": order.payment_status,
            "payment_installments": order.payment_installments,
            "fulfillment_type": order.fulfillment_type,
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
            "created_at": order.created_at
        }

    def get_order_tracking(self, order_number: str) -> Dict[str, Any]:
        order = self.commerce_repo.get_order_by_number(order_number)
        if not order:
            raise ResourceNotFoundError("Order", order_number)

        is_bopis = order.fulfillment_type == "bopis"

        if is_bopis:
            milestones = [
                {"status_key": "placed", "title": "Order Placed & Confirmed", "description": "Payment secured and routed to store warehouse.", "is_completed": True, "is_current": False},
                {"status_key": "processing", "title": "Store Preparing Items", "description": "Boutique associate pulling garments and verifying quality.", "is_completed": True, "is_current": True},
                {"status_key": "ready_for_pickup", "title": "Ready for Boutique Pickup", "description": f"Present pickup code {order.bopis_pickup_code} at checkout counter.", "is_completed": False, "is_current": False},
                {"status_key": "delivered", "title": "Collected by Customer", "description": "Pickup completed.", "is_completed": False, "is_current": False}
            ]
        else:
            milestones = [
                {"status_key": "placed", "title": "Order Placed", "description": "Order received and verified.", "is_completed": True, "is_current": False},
                {"status_key": "processing", "title": "Fulfillment & Quality Check", "description": "Garments steamed, packaged in luxury garment bag.", "is_completed": True, "is_current": True},
                {"status_key": "dispatched", "title": "Dispatched with Carrier", "description": "In transit with premium courier.", "is_completed": False, "is_current": False},
                {"status_key": "out_for_delivery", "title": "Out for Delivery", "description": "Driver on route to delivery address.", "is_completed": False, "is_current": False},
                {"status_key": "delivered", "title": "Delivered", "description": "Delivered to recipient.", "is_completed": False, "is_current": False}
            ]

        store_info = None
        if order.bopis_store:
            store_info = {
                "name": order.bopis_store.name,
                "address": order.bopis_store.address,
                "city": order.bopis_store.city,
                "pickup_instructions": order.bopis_store.pickup_instructions or "Visit Customer Service desk with your digital pickup code.",
                "pickup_code": order.bopis_pickup_code
            }

        return {
            "order_number": order.order_number,
            "current_status": order.status,
            "estimated_delivery": "2-3 business days" if not is_bopis else "Today by 6:00 PM",
            "carrier": "CONFIT Express Logistics" if not is_bopis else "In-Store Concierge",
            "tracking_number": order.tracking_number,
            "timeline": milestones,
            "bopis_store_info": store_info
        }

    def create_return(self, user_id: int, order_id: int, reason: str, details: Optional[str], item_ids: List[int]) -> Dict[str, Any]:
        order = self.db.query(Order).filter(Order.id == order_id, Order.user_id == user_id).first()
        if not order:
            raise ResourceNotFoundError("Order", order_id)

        refund_subtotal = sum(it.subtotal for it in order.items if it.id in item_ids)
        req = self.commerce_repo.create_return_request(
            order_id=order.id,
            user_id=user_id,
            reason=reason,
            details=details,
            refund_amount=refund_subtotal,
            item_ids=item_ids,
            try_on_used=order.try_on_assisted
        )

        return {
            "id": req.id,
            "return_number": req.return_number,
            "order_id": req.order_id,
            "status": req.status,
            "reason": req.reason,
            "refund_amount": req.refund_amount,
            "return_label_url": req.return_label_url,
            "created_at": req.created_at,
            "resolved_at": req.resolved_at
        }

    def _format_cart(self, cart: Cart) -> Dict[str, Any]:
        items_out = []
        subtotal = 0.0
        count = 0

        for it in (cart.items if cart and cart.items else []):
            sku = it.sku
            prod = sku.product
            price = sku.price_override or prod.base_price
            line_sub = price * it.quantity
            subtotal += line_sub
            count += it.quantity

            items_out.append({
                "id": it.id,
                "product_sku_id": sku.id,
                "product_id": prod.id,
                "product_title": prod.title,
                "product_title_ar": prod.title_ar,
                "brand_name": prod.brand.brand_name if prod.brand else "CONFIT",
                "size": sku.size,
                "color": sku.color,
                "unit_price": price,
                "quantity": it.quantity,
                "subtotal": line_sub,
                "image_url": prod.thumbnail_url,
                "ai_fit_verdict": "True to Size (Confidence 95%)",
                "outfit_id": it.outfit_id
            })

        discount = 0.0
        tax = round(subtotal * 0.05, 2)
        shipping = 0.0 if (subtotal >= 200 or subtotal == 0) else 15.0
        total = round(subtotal - discount + tax + shipping, 2)

        return {
            "id": cart.id if cart else 1,
            "items": items_out,
            "subtotal": subtotal,
            "discount_amount": discount,
            "tax_amount": tax,
            "shipping_amount": shipping,
            "total": total,
            "currency": "USD",
            "items_count": count,
            "bnpl_monthly_quote": round(total / 4, 2) if total > 0 else 0.0
        }
