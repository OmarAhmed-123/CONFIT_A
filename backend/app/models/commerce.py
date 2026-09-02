from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    Float,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class Cart(Base):
    __tablename__ = "carts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    session_token = Column(String(100), unique=True, index=True, nullable=False)
    status = Column(String(30), default="active", nullable=False)  # active | abandoned | converted
    promo_code = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    items = relationship("CartItem", back_populates="cart", cascade="all, delete-orphan")


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("cart_id", "product_sku_id", name="uq_cart_items_cart_sku"),
    )

    id = Column(Integer, primary_key=True, index=True)
    cart_id = Column(Integer, ForeignKey("carts.id", ondelete="CASCADE"), nullable=False)
    product_sku_id = Column(Integer, ForeignKey("product_skus.id", ondelete="CASCADE"), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    outfit_id = Column(Integer, ForeignKey("outfits.id", ondelete="SET NULL"), nullable=True)
    added_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    cart = relationship("Cart", back_populates="items")
    sku = relationship("ProductSKU")
    outfit = relationship("Outfit")


class Promotion(Base):
    __tablename__ = "promotions"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)
    description = Column(String(255), nullable=False)
    discount_type = Column(String(20), nullable=False)  # percent | fixed
    discount_value = Column(Float, nullable=False)
    min_order_amount = Column(Float, default=0.0, nullable=False)
    brand_id = Column(Integer, ForeignKey("brand_profiles.id", ondelete="SET NULL"), nullable=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    market = Column(String(10), nullable=True)
    currency = Column(String(10), default="USD", nullable=False)
    max_redemptions = Column(Integer, nullable=True)
    max_per_user = Column(Integer, default=1, nullable=False)
    stackable = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    starts_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    brand = relationship("BrandProfile")
    redemptions = relationship("PromotionRedemption", back_populates="promotion")


class PromotionRedemption(Base):
    __tablename__ = "promotion_redemptions"
    __table_args__ = (
        UniqueConstraint("promotion_id", "order_id", name="uq_promo_redemption_order"),
    )

    id = Column(Integer, primary_key=True, index=True)
    promotion_id = Column(Integer, ForeignKey("promotions.id", ondelete="CASCADE"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    guest_email = Column(String(255), nullable=True)
    discount_amount = Column(Float, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    promotion = relationship("Promotion", back_populates="redemptions")
    order = relationship("Order")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String(50), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    guest_email = Column(String(255), nullable=True, index=True)
    guest_session_token = Column(String(100), nullable=True, index=True)

    total_amount = Column(Float, nullable=False)
    subtotal_amount = Column(Float, nullable=False)
    discount_amount = Column(Float, default=0.0, nullable=False)
    tax_amount = Column(Float, default=0.0, nullable=False)
    shipping_amount = Column(Float, default=0.0, nullable=False)
    currency = Column(String(10), default="USD", nullable=False)
    promo_code = Column(String(50), nullable=True)

    payment_method = Column(String(50), default="card", nullable=False)
    payment_status = Column(String(30), default="pending", nullable=False)
    payment_installments = Column(Integer, default=1, nullable=False)
    payment_mode = Column(String(20), default="demo", nullable=False)  # demo | live

    fulfillment_type = Column(String(30), default="delivery", nullable=False)
    shipping_method = Column(String(30), default="standard", nullable=False)  # standard | express
    bopis_store_id = Column(Integer, ForeignKey("store_locations.id"), nullable=True)
    bopis_pickup_code = Column(String(20), nullable=True)
    ready_for_pickup_at = Column(DateTime, nullable=True)

    shipping_recipient_name = Column(String(255), nullable=True)
    shipping_address_line = Column(String(500), nullable=True)
    shipping_city = Column(String(100), nullable=True)
    shipping_country = Column(String(100), nullable=True)
    shipping_phone = Column(String(50), nullable=True)
    tracking_number = Column(String(100), nullable=True)
    estimated_delivery_date = Column(DateTime, nullable=True)

    status = Column(String(50), default="placed", nullable=False)
    try_on_assisted = Column(Boolean, default=False, nullable=False)
    stylist_assisted = Column(Boolean, default=False, nullable=False)
    idempotency_key = Column(String(100), unique=True, index=True, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    bopis_store = relationship("StoreLocation")
    return_requests = relationship("ReturnRequest", back_populates="order")
    payment_transactions = relationship("PaymentTransaction", back_populates="order")
    fulfillment_groups = relationship("FulfillmentGroup", back_populates="order")
    events = relationship("OrderEvent", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    product_sku_id = Column(Integer, ForeignKey("product_skus.id", ondelete="SET NULL"), nullable=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    brand_id = Column(Integer, ForeignKey("brand_profiles.id"), nullable=False)
    outfit_id = Column(Integer, ForeignKey("outfits.id", ondelete="SET NULL"), nullable=True)
    fulfillment_group_id = Column(
        Integer,
        ForeignKey(
            "fulfillment_groups.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_order_items_fulfillment_group",
        ),
        nullable=True,
    )

    product_title = Column(String(255), nullable=False)
    brand_name = Column(String(255), nullable=False)
    size = Column(String(20), nullable=False)
    color = Column(String(50), nullable=False)
    unit_price = Column(Float, nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    subtotal = Column(Float, nullable=False)
    is_returned = Column(Boolean, default=False, nullable=False)

    order = relationship("Order", back_populates="items")
    product = relationship("Product")
    brand = relationship("BrandProfile")
    outfit = relationship("Outfit")
    fulfillment_group = relationship("FulfillmentGroup", back_populates="items")


class OrderEvent(Base):
    """Append-only fulfillment / payment timeline. Tracking reads these rows."""

    __tablename__ = "order_events"
    __table_args__ = (Index("ix_order_events_order_created", "order_id", "created_at"),)

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    status_key = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    order = relationship("Order", back_populates="events")


class FulfillmentGroup(Base):
    """One shipment or store-pickup unit — typically one brand in a multi-brand order."""

    __tablename__ = "fulfillment_groups"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    brand_id = Column(Integer, ForeignKey("brand_profiles.id"), nullable=False)
    brand_name = Column(String(255), nullable=False)
    fulfillment_type = Column(String(30), nullable=False)  # delivery | bopis
    store_id = Column(Integer, ForeignKey("store_locations.id"), nullable=True)
    status = Column(String(50), default="processing", nullable=False)
    carrier = Column(String(100), nullable=True)
    tracking_number = Column(String(100), unique=True, nullable=True)
    estimated_delivery_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    order = relationship("Order", back_populates="fulfillment_groups")
    items = relationship("OrderItem", back_populates="fulfillment_group")
    shipments = relationship("Shipment", back_populates="fulfillment_group")


class Shipment(Base):
    __tablename__ = "shipments"

    id = Column(Integer, primary_key=True, index=True)
    fulfillment_group_id = Column(
        Integer, ForeignKey("fulfillment_groups.id", ondelete="CASCADE"), nullable=False
    )
    carrier = Column(String(100), nullable=False)
    tracking_number = Column(String(100), unique=True, index=True, nullable=False)
    status = Column(String(50), default="label_created", nullable=False)
    shipped_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    fulfillment_group = relationship("FulfillmentGroup", back_populates="shipments")


class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"
    __table_args__ = (
        UniqueConstraint("provider", "provider_tx_id", name="uq_payment_provider_tx"),
        UniqueConstraint("idempotency_key", name="uq_payment_idempotency"),
    )

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(50), nullable=False)
    method = Column(String(50), nullable=False)
    provider_tx_id = Column(String(100), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(10), nullable=False)
    status = Column(String(30), nullable=False)  # pending | authorized | captured | failed | refunded
    mode = Column(String(20), default="demo", nullable=False)
    idempotency_key = Column(String(100), nullable=True)
    refunded_amount = Column(Float, default=0.0, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    order = relationship("Order", back_populates="payment_transactions")


class WebhookEvent(Base):
    """Deduplicates PSP webhook deliveries by provider + event id."""

    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),)

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(50), nullable=False)
    event_id = Column(String(128), nullable=False)
    order_number = Column(String(50), nullable=True)
    processed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    status = Column(String(30), default="processed", nullable=False)


class CheckoutSession(Base):
    """
    Durable checkout session persistence - C2 Fix.
    Previously token was generated but never persisted (dead code, always 404).
    Now implements full lifecycle:
    - token persistence with ownership
    - cart snapshot (server-authoritative totals at session creation time)
    - expiration (30min default)
    - validation and invalidation
    - authorization (user_id or guest_email)
    - cleanup via expiry
    """

    __tablename__ = "checkout_sessions"
    __table_args__ = (
        Index("ix_checkout_sessions_user", "user_id"),
        Index("ix_checkout_sessions_expires", "expires_at"),
        Index("ix_checkout_sessions_status", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(100), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    guest_email = Column(String(255), nullable=True)
    guest_session_token = Column(String(100), nullable=True, index=True)

    cart_snapshot_json = Column(Text, nullable=False)  # Server-authoritative cart at session creation
    total_amount = Column(Float, nullable=False)
    currency = Column(String(10), default="USD", nullable=False)
    promo_code = Column(String(50), nullable=True)

    status = Column(String(30), default="active", nullable=False)  # active | converted | expired | cancelled
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)

    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    converted_at = Column(DateTime, nullable=True)

    user = relationship("User")
    order = relationship("Order")


class InventoryReservation(Base):
    __tablename__ = "inventory_reservations"
    __table_args__ = (Index("ix_inv_res_sku_status", "sku_id", "status"),)

    id = Column(Integer, primary_key=True, index=True)
    sku_id = Column(Integer, ForeignKey("product_skus.id", ondelete="CASCADE"), nullable=False)
    quantity = Column(Integer, nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    store_id = Column(Integer, ForeignKey("store_locations.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(20), default="held", nullable=False)  # held | committed | released
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    released_at = Column(DateTime, nullable=True)


class ReturnRequest(Base):
    __tablename__ = "return_requests"

    id = Column(Integer, primary_key=True, index=True)
    return_number = Column(String(50), unique=True, index=True, nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    guest_email = Column(String(255), nullable=True)

    reason = Column(String(100), nullable=False)
    details = Column(Text, nullable=True)
    refund_amount = Column(Float, nullable=False)
    return_label_url = Column(String(1000), nullable=True)
    label_provider_ref = Column(String(100), nullable=True)
    status = Column(String(30), default="requested", nullable=False)
    try_on_used_for_item = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    resolved_at = Column(DateTime, nullable=True)

    order = relationship("Order", back_populates="return_requests")
    items = relationship("ReturnItem", back_populates="return_request", cascade="all, delete-orphan")


class ReturnItem(Base):
    __tablename__ = "return_items"
    __table_args__ = (
        UniqueConstraint("return_request_id", "order_item_id", name="uq_return_item"),
    )

    id = Column(Integer, primary_key=True, index=True)
    return_request_id = Column(
        Integer, ForeignKey("return_requests.id", ondelete="CASCADE"), nullable=False
    )
    order_item_id = Column(Integer, ForeignKey("order_items.id", ondelete="CASCADE"), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)

    return_request = relationship("ReturnRequest", back_populates="items")
    order_item = relationship("OrderItem")


class ExchangeRequest(Base):
    __tablename__ = "exchange_requests"

    id = Column(Integer, primary_key=True, index=True)
    exchange_number = Column(String(50), unique=True, index=True, nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    original_item_id = Column(Integer, ForeignKey("order_items.id"), nullable=False)
    replacement_sku_id = Column(Integer, ForeignKey("product_skus.id"), nullable=False)
    price_delta = Column(Float, default=0.0, nullable=False)
    status = Column(String(30), default="requested", nullable=False)
    payment_status = Column(String(30), default="not_required", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    resolved_at = Column(DateTime, nullable=True)

    order = relationship("Order")
    original_item = relationship("OrderItem")
    replacement_sku = relationship("ProductSKU")
