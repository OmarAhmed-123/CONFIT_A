import uuid
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session, joinedload
from backend.app.models.commerce import Cart, CartItem, Order, OrderItem, ReturnRequest
from backend.app.models.catalog import ProductSKU, Product, StoreLocation


class CommerceRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create_cart(self, session_token: str, user_id: Optional[int] = None) -> Cart:
        cart = None
        if user_id:
            cart = self.db.query(Cart).filter(Cart.user_id == user_id, Cart.status == "active").first()
        if not cart and session_token:
            cart = self.db.query(Cart).filter(Cart.session_token == session_token, Cart.status == "active").first()

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

    def get_cart_with_items(self, cart_id: int) -> Optional[Cart]:
        return (
            self.db.query(Cart)
            .options(
                joinedload(Cart.items).joinedload(CartItem.sku).joinedload(ProductSKU.product).joinedload(Product.brand),
                joinedload(Cart.items).joinedload(CartItem.outfit)
            )
            .filter(Cart.id == cart_id)
            .first()
        )

    def add_to_cart(self, cart_id: int, product_sku_id: int, quantity: int = 1, outfit_id: Optional[int] = None) -> CartItem:
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
        else:
            item = CartItem(
                cart_id=cart_id,
                product_sku_id=product_sku_id,
                quantity=quantity,
                outfit_id=outfit_id
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

    def clear_cart(self, cart_id: int) -> None:
        self.db.query(CartItem).filter(CartItem.cart_id == cart_id).delete()
        self.db.commit()

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
        items: List[Dict[str, Any]]
    ) -> Order:
        order_number = f"CONF-{uuid.uuid4().hex[:8].upper()}"
        bopis_code = f"PICKUP-{uuid.uuid4().hex[:6].upper()}" if fulfillment_type == "bopis" else None
        tracking_num = f"TRK-{uuid.uuid4().hex[:10].upper()}"

        order = Order(
            order_number=order_number,
            user_id=user_id,
            total_amount=total_amount,
            subtotal_amount=subtotal_amount,
            discount_amount=discount_amount,
            tax_amount=tax_amount,
            shipping_amount=shipping_amount,
            currency=currency,
            payment_method=payment_method,
            payment_status=payment_status,
            payment_installments=payment_installments,
            fulfillment_type=fulfillment_type,
            bopis_store_id=bopis_store_id,
            bopis_pickup_code=bopis_code,
            shipping_recipient_name=shipping_details.get("recipient_name"),
            shipping_address_line=shipping_details.get("address_line"),
            shipping_city=shipping_details.get("city"),
            shipping_country=shipping_details.get("country", "UAE"),
            shipping_phone=shipping_details.get("phone"),
            tracking_number=tracking_num,
            status="placed" if fulfillment_type != "bopis" else "processing",
            try_on_assisted=try_on_assisted,
            stylist_assisted=stylist_assisted,
            idempotency_key=idempotency_key
        )
        self.db.add(order)
        self.db.flush()

        for item_data in items:
            order_item = OrderItem(
                order_id=order.id,
                product_sku_id=item_data.get("product_sku_id"),
                product_id=item_data["product_id"],
                brand_id=item_data["brand_id"],
                product_title=item_data["product_title"],
                brand_name=item_data["brand_name"],
                size=item_data["size"],
                color=item_data["color"],
                unit_price=item_data["unit_price"],
                quantity=item_data["quantity"],
                subtotal=item_data["subtotal"],
                is_returned=False
            )
            self.db.add(order_item)

        self.db.commit()
        self.db.refresh(order)
        return order

    def get_order_by_number(self, order_number: str) -> Optional[Order]:
        return (
            self.db.query(Order)
            .options(
                joinedload(Order.items).joinedload(OrderItem.product),
                joinedload(Order.items).joinedload(OrderItem.brand),
                joinedload(Order.bopis_store)
            )
            .filter(Order.order_number == order_number)
            .first()
        )

    def get_user_orders(self, user_id: int) -> List[Order]:
        return (
            self.db.query(Order)
            .options(
                joinedload(Order.items),
                joinedload(Order.bopis_store)
            )
            .filter(Order.user_id == user_id)
            .order_by(Order.created_at.desc())
            .all()
        )

    def create_return_request(
        self,
        order_id: int,
        user_id: int,
        reason: str,
        details: Optional[str],
        refund_amount: float,
        item_ids: List[int],
        try_on_used: bool = False
    ) -> ReturnRequest:
        return_number = f"RET-{uuid.uuid4().hex[:8].upper()}"
        return_label_url = f"https://api.confit.io/labels/{return_number}.pdf"

        req = ReturnRequest(
            return_number=return_number,
            order_id=order_id,
            user_id=user_id,
            reason=reason,
            details=details,
            refund_amount=refund_amount,
            return_label_url=return_label_url,
            status="approved",
            try_on_used_for_item=try_on_used
        )
        self.db.add(req)

        # Mark order items as returned
        self.db.query(OrderItem).filter(OrderItem.id.in_(item_ids)).update({"is_returned": True}, synchronize_session=False)

        self.db.commit()
        self.db.refresh(req)
        return req
