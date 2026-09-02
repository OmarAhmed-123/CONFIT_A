import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import update

from backend.app.models.commerce import (
    Cart,
    CartItem,
    Order,
    OrderItem,
    ReturnRequest,
    ReturnItem,
    Promotion,
    PromotionRedemption,
    PaymentTransaction,
    WebhookEvent,
    FulfillmentGroup,
    InventoryReservation,
    OrderEvent,
    ExchangeRequest,
)
from backend.app.models.catalog import ProductSKU, Product, StoreInventory


class CommerceRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create_cart(self, session_token: str, user_id: Optional[int] = None) -> Cart:
        cart = None
        if user_id:
            cart = (
                self.db.query(Cart)
                .options(joinedload(Cart.items))
                .filter(Cart.user_id == user_id, Cart.status == "active")
                .first()
            )
        if not cart and session_token:
            cart = (
                self.db.query(Cart)
                .options(joinedload(Cart.items))
                .filter(Cart.session_token == session_token, Cart.status == "active")
                .first()
            )

        if not cart:
            token = session_token or str(uuid.uuid4())
            cart = Cart(session_token=token, user_id=user_id, status="active")
            self.db.add(cart)
            self.db.commit()
            self.db.refresh(cart)
        elif user_id and not cart.user_id:
            cart.user_id = user_id
            self.db.commit()
            self.db.refresh(cart)

        return cart

    def merge_guest_into_user_cart(self, guest_token: str, user_id: int) -> Cart:
        """Move guest-cart lines into the authenticated user's active cart."""
        user_cart = self.get_or_create_cart(session_token=f"user-{user_id}", user_id=user_id)
        guest_cart = (
            self.db.query(Cart)
            .filter(Cart.session_token == guest_token, Cart.status == "active")
            .first()
        )
        if not guest_cart or guest_cart.id == user_cart.id:
            return self.get_cart_with_items(user_cart.id) or user_cart

        guest_full = self.get_cart_with_items(guest_cart.id)
        for item in list(guest_full.items if guest_full else []):
            self.add_to_cart(
                user_cart.id,
                item.product_sku_id,
                item.quantity,
                item.outfit_id,
            )
            self.db.delete(item)
        if guest_cart.promo_code and not user_cart.promo_code:
            user_cart.promo_code = guest_cart.promo_code
        guest_cart.status = "converted"
        self.db.commit()
        return self.get_cart_with_items(user_cart.id) or user_cart

    def get_cart_with_items(self, cart_id: int) -> Optional[Cart]:
        return (
            self.db.query(Cart)
            .options(
                joinedload(Cart.items).joinedload(CartItem.sku).joinedload(ProductSKU.product).joinedload(Product.brand),
                joinedload(Cart.items).joinedload(CartItem.outfit),
            )
            .filter(Cart.id == cart_id)
            .first()
        )

    def get_cart_item_for_cart(self, cart_id: int, cart_item_id: int) -> Optional[CartItem]:
        return (
            self.db.query(CartItem)
            .filter(CartItem.id == cart_item_id, CartItem.cart_id == cart_id)
            .first()
        )

    def add_to_cart(
        self,
        cart_id: int,
        product_sku_id: int,
        quantity: int = 1,
        outfit_id: Optional[int] = None,
    ) -> CartItem:
        existing = (
            self.db.query(CartItem)
            .filter(CartItem.cart_id == cart_id, CartItem.product_sku_id == product_sku_id)
            .first()
        )
        if existing:
            existing.quantity += quantity
            if outfit_id:
                existing.outfit_id = outfit_id
            self.db.commit()
            self.db.refresh(existing)
            return existing
        item = CartItem(
            cart_id=cart_id,
            product_sku_id=product_sku_id,
            quantity=quantity,
            outfit_id=outfit_id,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_cart_item_quantity(self, cart_item_id: int, quantity: int) -> Optional[CartItem]:
        item = self.db.query(CartItem).filter(CartItem.id == cart_item_id).first()
        if not item:
            return None
        if quantity <= 0:
            self.db.delete(item)
            self.db.commit()
            return None
        item.quantity = quantity
        self.db.commit()
        self.db.refresh(item)
        return item

    def remove_cart_item(self, cart_item_id: int) -> bool:
        item = self.db.query(CartItem).filter(CartItem.id == cart_item_id).first()
        if item:
            self.db.delete(item)
            self.db.commit()
            return True
        return False

    def set_cart_promo(self, cart_id: int, promo_code: Optional[str]) -> None:
        cart = self.db.query(Cart).filter(Cart.id == cart_id).first()
        if cart:
            cart.promo_code = promo_code
            self.db.commit()

    def clear_cart(self, cart_id: int) -> None:
        cart = self.db.query(Cart).filter(Cart.id == cart_id).first()
        self.db.query(CartItem).filter(CartItem.cart_id == cart_id).delete()
        if cart:
            cart.status = "converted"
            cart.promo_code = None
        self.db.commit()

    def get_promotion_by_code(self, code: str) -> Optional[Promotion]:
        return (
            self.db.query(Promotion)
            .filter(Promotion.code == code.upper().strip())
            .first()
        )

    def count_redemptions(self, promotion_id: int, user_id: Optional[int] = None) -> int:
        q = self.db.query(PromotionRedemption).filter(
            PromotionRedemption.promotion_id == promotion_id
        )
        if user_id:
            q = q.filter(PromotionRedemption.user_id == user_id)
        return q.count()

    def lock_sku(self, sku_id: int) -> Optional[ProductSKU]:
        return (
            self.db.query(ProductSKU)
            .with_for_update()
            .filter(ProductSKU.id == sku_id)
            .first()
        )

    def lock_store_inventory(self, store_id: int, sku_id: int) -> Optional[StoreInventory]:
        return (
            self.db.query(StoreInventory)
            .with_for_update()
            .filter(StoreInventory.store_id == store_id, StoreInventory.sku_id == sku_id)
            .first()
        )

    def get_order_by_idempotency(self, key: str) -> Optional[Order]:
        return self.db.query(Order).filter(Order.idempotency_key == key).first()

    def get_order_by_id(self, order_id: int) -> Optional[Order]:
        return (
            self.db.query(Order)
            .options(
                joinedload(Order.items),
                joinedload(Order.bopis_store),
                joinedload(Order.fulfillment_groups),
                joinedload(Order.events),
            )
            .filter(Order.id == order_id)
            .first()
        )

    def create_order(
        self,
        user_id: Optional[int],
        total_amount: float,
        subtotal_amount: float,
        discount_amount: float,
        tax_amount: float,
        shipping_amount: float,
        currency: str,
        payment_method: str,
        payment_status: str,
        payment_installments: int,
        fulfillment_type: str,
        bopis_store_id: Optional[int],
        shipping_details: Dict[str, Any],
        idempotency_key: Optional[str],
        try_on_assisted: bool,
        stylist_assisted: bool,
        items: List[Dict[str, Any]],
        guest_email: Optional[str] = None,
        guest_session_token: Optional[str] = None,
        promo_code: Optional[str] = None,
        payment_mode: str = "demo",
        shipping_method: str = "standard",
        estimated_delivery_date: Optional[datetime] = None,
    ) -> Order:
        order_number = f"CONF-{uuid.uuid4().hex[:8].upper()}"
        bopis_code = f"PICKUP-{uuid.uuid4().hex[:6].upper()}" if fulfillment_type == "bopis" else None

        order = Order(
            order_number=order_number,
            user_id=user_id,
            guest_email=guest_email,
            guest_session_token=guest_session_token,
            total_amount=total_amount,
            subtotal_amount=subtotal_amount,
            discount_amount=discount_amount,
            tax_amount=tax_amount,
            shipping_amount=shipping_amount,
            currency=currency,
            promo_code=promo_code,
            payment_method=payment_method,
            payment_status=payment_status,
            payment_installments=payment_installments,
            payment_mode=payment_mode,
            fulfillment_type=fulfillment_type,
            shipping_method=shipping_method,
            bopis_store_id=bopis_store_id,
            bopis_pickup_code=bopis_code,
            shipping_recipient_name=shipping_details.get("recipient_name"),
            shipping_address_line=shipping_details.get("address_line"),
            shipping_city=shipping_details.get("city"),
            shipping_country=shipping_details.get("country", "UAE"),
            shipping_phone=shipping_details.get("phone"),
            estimated_delivery_date=estimated_delivery_date,
            status="placed",
            try_on_assisted=try_on_assisted,
            stylist_assisted=stylist_assisted,
            idempotency_key=idempotency_key,
        )
        self.db.add(order)
        self.db.flush()

        # Brand-level fulfillment groups (one logical cart, partitioned internally).
        groups_by_brand: Dict[int, FulfillmentGroup] = {}
        for item_data in items:
            brand_id = item_data["brand_id"]
            if brand_id not in groups_by_brand:
                group = FulfillmentGroup(
                    order_id=order.id,
                    brand_id=brand_id,
                    brand_name=item_data["brand_name"],
                    fulfillment_type=fulfillment_type,
                    store_id=bopis_store_id if fulfillment_type == "bopis" else None,
                    status="processing",
                    # Carrier + tracking are assigned when a shipping provider
                    # actually creates a label. Never invent a TRK-* number.
                    carrier=None,
                    tracking_number=None,
                    estimated_delivery_date=estimated_delivery_date,
                )
                self.db.add(group)
                self.db.flush()
                groups_by_brand[brand_id] = group

            group = groups_by_brand[brand_id]
            order_item = OrderItem(
                order_id=order.id,
                product_sku_id=item_data.get("product_sku_id"),
                product_id=item_data["product_id"],
                brand_id=brand_id,
                outfit_id=item_data.get("outfit_id"),
                fulfillment_group_id=group.id,
                product_title=item_data["product_title"],
                brand_name=item_data["brand_name"],
                size=item_data["size"],
                color=item_data["color"],
                unit_price=item_data["unit_price"],
                quantity=item_data["quantity"],
                subtotal=item_data["subtotal"],
                is_returned=False,
            )
            self.db.add(order_item)

        self.db.add(
            OrderEvent(
                order_id=order.id,
                status_key="placed",
                title="Order placed",
                description="Order recorded. Payment confirmation is pending provider status.",
            )
        )
        self.db.commit()
        self.db.refresh(order)
        return order

    def add_order_event(self, order_id: int, status_key: str, title: str, description: str) -> None:
        self.db.add(
            OrderEvent(
                order_id=order_id,
                status_key=status_key,
                title=title,
                description=description,
            )
        )
        self.db.commit()

    def get_order_by_number(self, order_number: str) -> Optional[Order]:
        return (
            self.db.query(Order)
            .options(
                joinedload(Order.items).joinedload(OrderItem.product),
                joinedload(Order.items).joinedload(OrderItem.brand),
                joinedload(Order.bopis_store),
                joinedload(Order.fulfillment_groups),
                joinedload(Order.events),
                joinedload(Order.payment_transactions),
            )
            .filter(Order.order_number == order_number)
            .first()
        )

    def get_user_orders(self, user_id: int) -> List[Order]:
        return (
            self.db.query(Order)
            .options(
                joinedload(Order.items),
                joinedload(Order.bopis_store),
            )
            .filter(Order.user_id == user_id)
            .order_by(Order.created_at.desc())
            .all()
        )

    def create_payment_transaction(
        self,
        order_id: int,
        provider: str,
        method: str,
        provider_tx_id: str,
        amount: float,
        currency: str,
        status: str,
        mode: str,
        idempotency_key: Optional[str],
    ) -> PaymentTransaction:
        existing = None
        if idempotency_key:
            existing = (
                self.db.query(PaymentTransaction)
                .filter(PaymentTransaction.idempotency_key == idempotency_key)
                .first()
            )
        if existing:
            return existing
        tx = PaymentTransaction(
            order_id=order_id,
            provider=provider,
            method=method,
            provider_tx_id=provider_tx_id,
            amount=amount,
            currency=currency,
            status=status,
            mode=mode,
            idempotency_key=idempotency_key,
        )
        self.db.add(tx)
        self.db.commit()
        self.db.refresh(tx)
        return tx

    def get_webhook_event(self, provider: str, event_id: str) -> Optional[WebhookEvent]:
        return (
            self.db.query(WebhookEvent)
            .filter(WebhookEvent.provider == provider, WebhookEvent.event_id == event_id)
            .first()
        )

    def record_webhook_event(
        self, provider: str, event_id: str, order_number: Optional[str], status: str = "processed"
    ) -> WebhookEvent:
        row = WebhookEvent(
            provider=provider,
            event_id=event_id,
            order_number=order_number,
            status=status,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def create_return_request(
        self,
        order_id: int,
        user_id: Optional[int],
        reason: str,
        details: Optional[str],
        refund_amount: float,
        item_ids: List[int],
        try_on_used: bool = False,
        return_label_url: Optional[str] = None,
        label_provider_ref: Optional[str] = None,
        guest_email: Optional[str] = None,
    ) -> ReturnRequest:
        return_number = f"RET-{uuid.uuid4().hex[:8].upper()}"
        req = ReturnRequest(
            return_number=return_number,
            order_id=order_id,
            user_id=user_id,
            guest_email=guest_email,
            reason=reason,
            details=details,
            refund_amount=refund_amount,
            return_label_url=return_label_url,
            label_provider_ref=label_provider_ref,
            status="requested",
            try_on_used_for_item=try_on_used,
        )
        self.db.add(req)
        self.db.flush()

        for item_id in item_ids:
            self.db.add(ReturnItem(return_request_id=req.id, order_item_id=item_id, quantity=1))
        self.db.query(OrderItem).filter(OrderItem.id.in_(item_ids)).update(
            {"is_returned": True}, synchronize_session=False
        )
        self.db.commit()
        self.db.refresh(req)
        return req

    def get_return_by_id(self, return_id: int) -> Optional[ReturnRequest]:
        return (
            self.db.query(ReturnRequest)
            .options(joinedload(ReturnRequest.items), joinedload(ReturnRequest.order))
            .filter(ReturnRequest.id == return_id)
            .first()
        )

    def create_exchange(
        self,
        order_id: int,
        user_id: Optional[int],
        original_item_id: int,
        replacement_sku_id: int,
        price_delta: float,
        payment_status: str,
    ) -> ExchangeRequest:
        req = ExchangeRequest(
            exchange_number=f"EXC-{uuid.uuid4().hex[:8].upper()}",
            order_id=order_id,
            user_id=user_id,
            original_item_id=original_item_id,
            replacement_sku_id=replacement_sku_id,
            price_delta=price_delta,
            status="requested",
            payment_status=payment_status,
        )
        self.db.add(req)
        self.db.commit()
        self.db.refresh(req)
        return req
