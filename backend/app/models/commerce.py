from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class Cart(Base):
    __tablename__ = "carts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    session_token = Column(String(100), unique=True, index=True, nullable=False)
    status = Column(String(30), default="active", nullable=False) # "active", "abandoned", "converted"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    items = relationship("CartItem", back_populates="cart", cascade="all, delete-orphan")


class CartItem(Base):
    __tablename__ = "cart_items"

    id = Column(Integer, primary_key=True, index=True)
    cart_id = Column(Integer, ForeignKey("carts.id", ondelete="CASCADE"), nullable=False)
    product_sku_id = Column(Integer, ForeignKey("product_skus.id", ondelete="CASCADE"), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    outfit_id = Column(Integer, ForeignKey("outfits.id", ondelete="SET NULL"), nullable=True)
    added_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    cart = relationship("Cart", back_populates="items")
    sku = relationship("ProductSKU")
    outfit = relationship("Outfit")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String(50), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    total_amount = Column(Float, nullable=False)
    subtotal_amount = Column(Float, nullable=False)
    discount_amount = Column(Float, default=0.0, nullable=False)
    tax_amount = Column(Float, default=0.0, nullable=False)
    shipping_amount = Column(Float, default=0.0, nullable=False)
    currency = Column(String(10), default="USD", nullable=False)

    payment_method = Column(String(50), default="card", nullable=False)  # "card", "bnpl_tabby", "bnpl_tamara", "cod", "apple_pay"
    payment_status = Column(String(30), default="paid", nullable=False)   # "pending", "authorized", "paid", "refunded", "failed"
    payment_installments = Column(Integer, default=1, nullable=False)     # e.g., 4 for BNPL

    fulfillment_type = Column(String(30), default="delivery", nullable=False) # "delivery", "bopis"
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

    status = Column(String(50), default="placed", nullable=False) # "placed", "processing", "dispatched", "out_for_delivery", "ready_for_pickup", "delivered", "returned", "cancelled"
    try_on_assisted = Column(Boolean, default=False, nullable=False)
    stylist_assisted = Column(Boolean, default=False, nullable=False)
    idempotency_key = Column(String(100), unique=True, index=True, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    bopis_store = relationship("StoreLocation")
    return_requests = relationship("ReturnRequest", back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    product_sku_id = Column(Integer, ForeignKey("product_skus.id", ondelete="SET NULL"), nullable=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    brand_id = Column(Integer, ForeignKey("brand_profiles.id"), nullable=False)

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


class ReturnRequest(Base):
    __tablename__ = "return_requests"

    id = Column(Integer, primary_key=True, index=True)
    return_number = Column(String(50), unique=True, index=True, nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    reason = Column(String(100), nullable=False) # "Wrong Size", "Color Difference", "Changed Mind", "Style Mismatch"
    details = Column(Text, nullable=True)
    refund_amount = Column(Float, nullable=False)
    return_label_url = Column(String(1000), nullable=True)
    status = Column(String(30), default="requested", nullable=False) # "requested", "approved", "shipped", "received", "refunded", "rejected"
    try_on_used_for_item = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    resolved_at = Column(DateTime, nullable=True)

    order = relationship("Order", back_populates="return_requests")
