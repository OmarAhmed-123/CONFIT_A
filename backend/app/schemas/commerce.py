from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional
from decimal import Decimal, ROUND_HALF_UP
from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, model_validator
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


# ── Money at the JSON boundary ─────────────────────────────────────────────
# Money is a Decimal everywhere it is COMPUTED (core.money). At the boundary it
# is declared as Decimal here too, so no float arithmetic is reachable inside
# the contract, and every figure is quantised to 2dp with ROUND_HALF_UP on the
# way out. Previously OrderItemOut.net_amount did
# ``round(float(subtotal) - float(discount or 0.0), 2)`` — a float subtraction
# inside the response model, which is precisely the kind of thing that drifts.
#
# The serialised type stays a JSON *number* rather than a string: the storefront
# types these fields as ``number`` (frontend/src/models/index.ts) and does
# arithmetic on them (cartStore multiplies unit_price by quantity), so emitting
# strings would break the client contract. A 2dp value round-trips exactly
# through a double within NUMERIC(12,2), so the number form is exact in range --
# see backend/tests/test_money_boundary_decimal.py for the proof.
_CENT = Decimal("0.01")


def _money_to_json(value: Any) -> float:
    """Serialise a monetary Decimal as an exact 2-decimal-place JSON number."""
    if value is None:
        return 0.0
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return float(value.quantize(_CENT, rounding=ROUND_HALF_UP))


#: Monetary field type: exact ``Decimal`` in Python, exact 2dp number on the wire.
Money = Annotated[
    Decimal,
    PlainSerializer(_money_to_json, return_type=float, when_used="json"),
]


class CartItemOut(BaseModel):
    id: int
    product_sku_id: int
    product_id: int
    product_title: str
    product_title_ar: str
    brand_name: str
    size: str
    color: str
    unit_price: Money
    quantity: int
    subtotal: Money
    image_url: str
    ai_fit_verdict: str
    in_stock: bool = True
    outfit_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class CartOut(BaseModel):
    id: int
    items: List[CartItemOut]
    subtotal: Money
    discount_amount: Money
    tax_amount: Money
    shipping_amount: Money
    #: The delivery method this quote actually priced (CUS-01). Previously the
    #: cart silently quoted standard no matter what checkout would charge.
    shipping_method: str = "standard"
    total: Money
    currency: str = "USD"
    items_count: int
    bnpl_monthly_quote: float
    #: True when the figure above is an illustrative estimate rather than an
    #: offer: no live PSP adapter exists for the provider (see bnpl_is_live()).
    bnpl_is_estimate: bool = True
    promo_code: Optional[str] = None
    brands: List[str] = []
    fit_summary: List[Dict[str, Any]] = []
    outfit_groups: List[Dict[str, Any]] = []


class CheckoutRequest(BaseModel):
    """Checkout intake. Carries NO monetary field, by design.

    Every amount on the resulting order is recomputed server-side from the cart
    and the catalog (see CommerceService.checkout). ``extra="forbid"`` makes
    that contract explicit at the boundary: a client that POSTs ``total``,
    ``discount_amount`` or any other unknown key gets a 422 naming the field,
    instead of the earlier behaviour where the value was accepted and silently
    dropped. Silence is what made "ignored" indistinguishable from "honoured"
    to anyone reading the code.
    """

    model_config = ConfigDict(extra="forbid")

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
    unit_price: Money
    quantity: int
    subtotal: Money
    #: This line's apportioned share of the order-level promo discount
    #: (migration 0025, largest-remainder allocation).
    #:
    #: The column was populated and conserved in the database from the start,
    #: but never exposed here — so an order that really carried an 18.00
    #: discount returned `discount_amount: null` on every line, and neither
    #: the shopper nor the brand could see where the money went. The value
    #: existed; the contract hid it.
    discount_amount: Money = Decimal("0.00")
    #: subtotal - discount_amount. Served rather than left to each client to
    #: recompute, because a client that forgets the subtraction shows the
    #: pre-discount figure as if it were what was charged.
    net_amount: Money = Decimal("0.00")
    is_returned: bool
    outfit_id: Optional[int] = None
    fulfillment_group_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def _derive_net(self):
        """net = subtotal - discount, computed once on the server.

        Done here so every endpoint returning an order line agrees, instead
        of each caller subtracting (or forgetting to).
        """
        gross = self.subtotal if isinstance(self.subtotal, Decimal) else Decimal(str(self.subtotal))
        disc = self.discount_amount or Decimal("0.00")
        if not isinstance(disc, Decimal):
            disc = Decimal(str(disc))
        # Exact Decimal subtraction, quantised once. No float() anywhere on the
        # money path — that was the only float arithmetic in this contract.
        object.__setattr__(
            self, "net_amount", (gross - disc).quantize(_CENT, rounding=ROUND_HALF_UP)
        )
        return self


class OrderOut(BaseModel):
    id: int
    order_number: str
    status: str
    total_amount: Money
    subtotal_amount: Money
    discount_amount: Money
    tax_amount: Money
    shipping_amount: Money
    currency: str
    #: Denomination of the price book the amounts were converted FROM, and the
    #: exact rate used. Null for orders created before migration 0028; the
    #: null is deliberate — a back-filled guess at read time would look like
    #: recorded provenance without being any.
    pricing_currency: Optional[str] = None
    fx_rate_used: Optional[float] = None
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
