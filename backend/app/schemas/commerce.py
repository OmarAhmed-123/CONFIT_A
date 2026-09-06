from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from backend.app.schemas.money_types import PositiveMoney


class CartItemAdd(BaseModel):
    product_sku_id: int
    quantity: int = Field(default=1, ge=1, le=10)
    outfit_id: Optional[int] = None
    override_duplicate_warning: bool = False


class CartItemQuantityUpdate(BaseModel):
    quantity: int = Field(ge=0, le=10)


class PromoApplyRequest(BaseModel):
    promo_code: Optional[str] = None


class CartItemOut(BaseModel):
    id: int
    product_sku_id: int
    product_id: int
    product_title: str
    product_title_ar: str
    brand_name: str
    size: str
    color: str
    unit_price: float
    quantity: int
    subtotal: float
    image_url: str
    ai_fit_verdict: str
    in_stock: bool = True
    outfit_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class CartOut(BaseModel):
    id: int
    items: List[CartItemOut]
    subtotal: float
    discount_amount: float
    tax_amount: float
    shipping_amount: float
    total: float
    currency: str = "USD"
    items_count: int
    bnpl_monthly_quote: float
    promo_code: Optional[str] = None
    brands: List[str] = []
    fit_summary: List[Dict[str, Any]] = []
    outfit_groups: List[Dict[str, Any]] = []


class CheckoutRequest(BaseModel):
    payment_method: str = Field(description="'card', 'bnpl_tabby', 'bnpl_tamara', 'apple_pay', 'cod'")
    fulfillment_type: str = Field(description="'delivery' or 'bopis'")
    bopis_store_id: Optional[int] = None
    recipient_name: str
    phone: str
    address_line: Optional[str] = None
    city: str
    country: str = "UAE"
    promo_code: Optional[str] = None
    idempotency_key: Optional[str] = None
    try_on_assisted: bool = False
    stylist_assisted: bool = False
    guest_email: Optional[str] = None
    shipping_method: str = "standard"


class OrderItemOut(BaseModel):
    id: int
    product_id: int
    product_title: str
    brand_name: str
    size: str
    color: str
    unit_price: float
    quantity: int
    subtotal: float
    is_returned: bool
    outfit_id: Optional[int] = None
    fulfillment_group_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class OrderOut(BaseModel):
    id: int
    order_number: str
    status: str
    total_amount: float
    subtotal_amount: float
    discount_amount: float
    tax_amount: float
    shipping_amount: float
    currency: str
    payment_method: str
    payment_status: str
    payment_installments: int
    fulfillment_type: str
    bopis_store_name: Optional[str] = None
    bopis_pickup_code: Optional[str] = None
    shipping_recipient_name: Optional[str] = None
    shipping_address_line: Optional[str] = None
    shipping_city: Optional[str] = None
    tracking_number: Optional[str] = None
    estimated_delivery_date: Optional[datetime] = None
    try_on_assisted: bool
    stylist_assisted: bool
    items: List[OrderItemOut]
    created_at: datetime
    user_id: Optional[int] = None
    guest_email: Optional[str] = None
    promo_code: Optional[str] = None
    payment_mode: Optional[str] = None
    shipping_method: Optional[str] = None
    fulfillment_groups: List[Dict[str, Any]] = []
    outfit_groups: List[Dict[str, Any]] = []

    model_config = ConfigDict(from_attributes=True)


class TrackingMilestone(BaseModel):
    status_key: str
    title: str
    description: str
    timestamp: Optional[datetime] = None
    is_completed: bool
    is_current: bool


class OrderTrackingTimelineOut(BaseModel):
    order_number: str
    current_status: str
    estimated_delivery: Optional[str]
    carrier: Optional[str] = None
    tracking_number: Optional[str] = None
    timeline: List[TrackingMilestone]
    bopis_store_info: Optional[Dict[str, Any]] = None
    shipments: List[Dict[str, Any]] = []


class ReturnRequestCreate(BaseModel):
    order_id: int
    reason: str
    details: Optional[str] = None
    item_ids: List[int]


class ReturnRequestOut(BaseModel):
    id: int
    return_number: str
    order_id: int
    status: str
    reason: str
    refund_amount: float
    return_label_url: str
    created_at: datetime
    resolved_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ExchangeCreate(BaseModel):
    order_id: int
    original_item_id: int
    replacement_sku_id: int


class ExchangeOut(BaseModel):
    id: int
    exchange_number: str
    order_id: int
    original_item_id: int
    replacement_sku_id: int
    price_delta: float
    status: str
    payment_status: str
    created_at: datetime


class BNPLQuoteRequest(BaseModel):
    amount: PositiveMoney
    currency: str = "USD"
    provider: str = "tabby"


class BNPLQuoteResponse(BaseModel):
    provider: str
    eligible: bool
    installments_count: int
    installment_amount: Optional[float] = None
    payment_schedule: List[Dict[str, Any]]
    disclaimer: str


class OrderTransitionRequest(BaseModel):
    """PAY-01: admin order-status transition target (ORDER_TRANSITIONS machine)."""

    new_status: str = Field(description="Target status, e.g. 'shipped', 'out_for_delivery', 'delivered'.")
