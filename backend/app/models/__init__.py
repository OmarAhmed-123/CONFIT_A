from backend.app.models.user import User, UserRole, BrandProfile, AuditLog, RefreshToken, PasswordResetToken, EmailVerificationToken, MFABackupCode, MFAEmailCode
from backend.app.models.profile import UserStyleProfile, MoodBoard, MoodBoardItem, UserWishlistItem
from backend.app.models.catalog import Category, Product, ProductSKU, StoreLocation, StoreInventory
from backend.app.models.stylist import StylistSession, StylistMessage, Outfit, OutfitItem
from backend.app.models.tryon import TryOnSession, VisualSearchQuery, MeasurementSession, MeasurementResult
from backend.app.models.wardrobe import WardrobeItem, WardrobeGapAnalysis
from backend.app.models.commerce import (
    Cart,
    CartItem,
    Order,
    OrderItem,
    ReturnRequest,
    Promotion,
    PromotionRedemption,
    PaymentTransaction,
    WebhookEvent,
    FulfillmentGroup,
    Shipment,
    InventoryReservation,
    OrderEvent,
    ReturnItem,
    ExchangeRequest,
    CheckoutSession,
)
from backend.app.models.brand_analytics import SponsoredPlacement, StyleHeatmapAggregate, AdLedgerEntry
# Registered here so Base.metadata is complete wherever ``backend.app.models``
# is imported (alembic env.py, the schema-drift gate, create_all in dev).
# Without this, autogenerate would propose DROPPING brand_analytics_events /
# catalog_import_jobs because it could not see their mappers.
from backend.app.models.catalog_import import CatalogImportJob, BrandAnalyticsEvent
from backend.app.models.membership import BrandMembership, BrandInvitation
# Email outbox (spec 15): registered so create_all/alembic autogenerate see it.
from backend.app.models.email_outbox import EmailOutbox
from backend.app.models.email_preference import EmailPreference
# In-app notifications (polling REST; serverless-safe). Registered so
# create_all/alembic autogenerate and the schema-drift gate see the mapper.
from backend.app.models.notification import Notification

__all__ = [
    "User",
    "UserRole",
    "BrandProfile",
    "AuditLog",
    "RefreshToken",
    "PasswordResetToken",
    "EmailVerificationToken",
    "MFABackupCode",
    "MFAEmailCode",
    "UserStyleProfile",
    "MoodBoard",
    "MoodBoardItem",
    "UserWishlistItem",
    "Category",
    "Product",
    "ProductSKU",
    "StoreLocation",
    "StoreInventory",
    "StylistSession",
    "StylistMessage",
    "Outfit",
    "OutfitItem",
    "TryOnSession",
    "VisualSearchQuery",
    "MeasurementSession",
    "MeasurementResult",
    "WardrobeItem",
    "WardrobeGapAnalysis",
    "Cart",
    "CartItem",
    "Order",
    "OrderItem",
    "ReturnRequest",
    "Promotion",
    "PromotionRedemption",
    "PaymentTransaction",
    "WebhookEvent",
    "FulfillmentGroup",
    "Shipment",
    "InventoryReservation",
    "OrderEvent",
    "ReturnItem",
    "ExchangeRequest",
    "CheckoutSession",
    "SponsoredPlacement",
    "AdLedgerEntry",
    "StyleHeatmapAggregate",
    "CatalogImportJob",
    "BrandAnalyticsEvent",
    "BrandMembership",
    "BrandInvitation",
    "Notification",
]
