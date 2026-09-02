from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    name_ar = Column(String(100), nullable=False)
    slug = Column(String(100), unique=True, index=True, nullable=False)
    parent_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    icon_name = Column(String(50), default="hanger")

    parent = relationship("Category", remote_side=[id], backref="subcategories")
    products = relationship("Product", back_populates="category")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brand_profiles.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    title = Column(String(255), nullable=False, index=True)
    title_ar = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, index=True, nullable=False)
    description = Column(Text, nullable=False)
    description_ar = Column(Text, nullable=False)
    base_price = Column(Float, nullable=False)
    currency = Column(String(10), default="USD", nullable=False)
    material = Column(String(255), nullable=True)
    care_instructions = Column(String(500), nullable=True)

    # Styling and AI taxonomy
    style_tags = Column(Text, default="[]", nullable=False)       # JSON: ["smart_casual", "minimalist"]
    occasion_tags = Column(Text, default="[]", nullable=False)    # JSON: ["work", "dinner", "casual"]
    color_family = Column(String(50), nullable=False)            # e.g., "Navy Blue"
    dominant_hex = Column(String(20), default="#1B1F3B")         # e.g., "#1B1F3B"
    thumbnail_url = Column(String(1000), nullable=False)
    images = Column(Text, default="[]", nullable=False)          # JSON list of image URLs
    size_chart_json = Column(Text, default="{}", nullable=False) # JSON measurement mappings

    rating = Column(Float, default=4.8)
    review_count = Column(Integer, default=42)
    style_compatibility_base = Column(Integer, default=85)       # Base compatibility %
    is_active = Column(Boolean, default=True, nullable=False)
    is_featured = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    brand = relationship("BrandProfile", back_populates="products")
    category = relationship("Category", back_populates="products")
    skus = relationship("ProductSKU", back_populates="product", cascade="all, delete-orphan")
    sponsored_placements = relationship("SponsoredPlacement", back_populates="product")


class ProductSKU(Base):
    __tablename__ = "product_skus"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    sku_code = Column(String(100), unique=True, index=True, nullable=False)
    size = Column(String(20), nullable=False)      # e.g., "S", "M", "L", "XL", "32x30"
    color = Column(String(50), nullable=False)     # e.g., "Midnight Navy"
    color_hex = Column(String(20), default="#1B1F3B")
    price_override = Column(Float, nullable=True)
    stock_level = Column(Integer, default=20, nullable=False)
    is_in_stock = Column(Boolean, default=True, nullable=False)

    product = relationship("Product", back_populates="skus")
    store_inventories = relationship("StoreInventory", back_populates="sku", cascade="all, delete-orphan")


class RecentlyViewed(Base):
    """Per-user recently-viewed product history for the Home Dashboard (G2.4).

    One row per (user, product) — re-viewing a product updates `viewed_at` and
    moves it to the front of the recency list (upsert semantics). Guests are not
    tracked; only authenticated users persist history.
    """
    __tablename__ = "recently_viewed"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    viewed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    product = relationship("Product")


class StoreLocation(Base):
    __tablename__ = "store_locations"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brand_profiles.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    name_ar = Column(String(255), nullable=False)
    address = Column(String(500), nullable=False)
    city = Column(String(100), nullable=False)
    country = Column(String(100), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    phone = Column(String(50), nullable=True)
    pickup_instructions = Column(Text, nullable=True)
    is_bopis_enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    brand = relationship("BrandProfile", back_populates="stores")
    inventories = relationship("StoreInventory", back_populates="store", cascade="all, delete-orphan")


class StoreInventory(Base):
    __tablename__ = "store_inventories"
    __table_args__ = (
        UniqueConstraint("store_id", "sku_id", name="uq_store_inventories_store_sku"),
    )

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("store_locations.id", ondelete="CASCADE"), nullable=False)
    sku_id = Column(Integer, ForeignKey("product_skus.id", ondelete="CASCADE"), nullable=False)
    quantity = Column(Integer, default=5, nullable=False)
    reserved_quantity = Column(Integer, default=0, nullable=False)

    store = relationship("StoreLocation", back_populates="inventories")
    sku = relationship("ProductSKU", back_populates="store_inventories")
