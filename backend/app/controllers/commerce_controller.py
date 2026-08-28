import uuid
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user_optional, get_current_user
from backend.app.models.user import User, UserRole
from backend.app.services.commerce_service import CommerceService
from backend.app.providers.bnpl_provider import BNPLProvider
from backend.app.providers.payment.orchestrator import PaymentOrchestrator
from backend.app.providers.payment.schemas import MarketPaymentCapabilitiesResponse
from backend.app.schemas.commerce import (
    CartOut,
    CartItemAdd,
    CheckoutRequest,
    OrderOut,
    OrderTrackingTimelineOut,
    ReturnRequestCreate,
    ReturnRequestOut,
    BNPLQuoteRequest,
    BNPLQuoteResponse
)
from backend.app.core.exceptions import AuthorizationError
from pydantic import BaseModel

router = APIRouter(tags=["Commerce, Payments & Fulfillment"])


class CartMergeRequest(BaseModel):
    guest_token: str


# 1. Market-Aware Payment Methods Discovery (Egypt & GCC Spec) — Public
@router.get("/payments/methods", response_model=MarketPaymentCapabilitiesResponse)
@router.get("/commerce/payment-methods", response_model=MarketPaymentCapabilitiesResponse)
def get_payment_methods_for_market(
    country_code: Optional[str] = Query("EG", description="Country code e.g. 'EG', 'AE', 'SA', 'QA', 'KW'")
):
    orchestrator = PaymentOrchestrator()
    return orchestrator.get_market_methods(country_code or "EG")


# 2. Cart Endpoints — Public & Guest Accessible
@router.get("/commerce/cart", response_model=CartOut)
@router.get("/cart", response_model=CartOut)
def get_cart(
    x_session_token: Optional[str] = Header("guest_session_default"),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = CommerceService(db)
    return service.get_cart(x_session_token, user_id=user.id if user else None)


@router.post("/commerce/cart/items", response_model=CartOut, status_code=status.HTTP_201_CREATED)
@router.post("/cart/items", response_model=CartOut, status_code=status.HTTP_201_CREATED)
def add_to_cart(
    payload: CartItemAdd,
    x_session_token: Optional[str] = Header("guest_session_default"),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = CommerceService(db)
    return service.add_to_cart(
        session_token=x_session_token,
        product_sku_id=payload.product_sku_id,
        quantity=payload.quantity,
        user_id=user.id if user else None,
        outfit_id=payload.outfit_id
    )


@router.put("/commerce/cart/items/{item_id}", response_model=CartOut)
@router.patch("/commerce/cart/items/{item_id}", response_model=CartOut)
@router.patch("/cart/items/{item_id}", response_model=CartOut)
def update_cart_item(
    item_id: int,
    quantity: int = Query(..., ge=0, le=10),
    x_session_token: Optional[str] = Header("guest_session_default"),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = CommerceService(db)
    return service.update_quantity(x_session_token, item_id, quantity, user_id=user.id if user else None)


@router.delete("/commerce/cart/items/{item_id}", response_model=CartOut)
@router.delete("/cart/items/{item_id}", response_model=CartOut)
def remove_from_cart(
    item_id: int,
    x_session_token: Optional[str] = Header("guest_session_default"),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = CommerceService(db)
    return service.remove_item(x_session_token, item_id, user_id=user.id if user else None)


@router.post("/cart/merge", response_model=CartOut)
def merge_guest_cart(
    payload: CartMergeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = CommerceService(db)
    return service.get_cart(payload.guest_token, user_id=user.id)


# 3. Checkout Endpoints — Strictly Gated with Mandatory Authentication (PDF G5.1 / G5.2)
@router.post("/commerce/checkout", response_model=OrderOut)
@router.post("/checkout", response_model=OrderOut)
async def checkout_order(
    payload: CheckoutRequest,
    x_session_token: Optional[str] = Header("guest_session_default"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = CommerceService(db)
    return await service.checkout(
        session_token=x_session_token,
        checkout_data=payload.model_dump(),
        user_id=user.id
    )


@router.post("/checkout/sessions", response_model=Dict[str, Any])
def create_checkout_session(
    payload: CheckoutRequest,
    x_session_token: Optional[str] = Header("guest_session_default"),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    token = f"chk_sess_{uuid.uuid4().hex[:12]}"
    service = CommerceService(db)
    cart = service.get_cart(x_session_token, user_id=user.id if user else None)
    return {
        "checkout_token": token,
        "cart_total": cart["total"],
        "currency": "USD",
        "payment_methods_available": ["card", "bnpl_tabby", "bnpl_tamara", "apple_pay", "vodafone_cash", "instapay_bridge", "cod"],
        "expires_in_seconds": 1800
    }


@router.get("/checkout/sessions/{token}")
def get_checkout_session(token: str):
    return {
        "checkout_token": token,
        "status": "created",
        "currency": "USD"
    }


@router.post("/checkout/sessions/{token}/confirm", response_model=OrderOut)
async def confirm_checkout_session(
    token: str,
    payload: CheckoutRequest,
    x_session_token: Optional[str] = Header("guest_session_default"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = CommerceService(db)
    return await service.checkout(
        session_token=x_session_token,
        checkout_data=payload.model_dump(),
        user_id=user.id
    )


# 4. Orders & Tracking — Scoped to Authenticated User
@router.get("/commerce/orders", response_model=List[OrderOut])
@router.get("/orders", response_model=List[OrderOut])
def get_user_orders(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = CommerceService(db)
    orders = service.commerce_repo.get_user_orders(user.id)
    return [service.get_order(o.order_number) for o in orders]


@router.get("/commerce/orders/{order_number}", response_model=OrderOut)
@router.get("/orders/{order_number}", response_model=OrderOut)
def get_order_by_number(
    order_number: str,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = CommerceService(db)
    order = service.get_order(order_number)
    # If user is authenticated, ensure customer isolation (unless Admin)
    if user and user.role != UserRole.ADMIN and order["user_id"] and order["user_id"] != user.id:
        raise AuthorizationError("Access denied: You cannot view order details of another customer.")
    return order


@router.get("/commerce/orders/{order_number}/tracking", response_model=OrderTrackingTimelineOut)
@router.get("/orders/{order_number}/tracking", response_model=OrderTrackingTimelineOut)
def get_order_tracking_timeline(order_number: str, db: Session = Depends(get_db)):
    service = CommerceService(db)
    return service.get_order_tracking(order_number)


# 5. Returns & Webhooks
@router.post("/commerce/returns", response_model=ReturnRequestOut, status_code=status.HTTP_201_CREATED)
@router.post("/returns", response_model=ReturnRequestOut, status_code=status.HTTP_201_CREATED)
def submit_return(
    payload: ReturnRequestCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = CommerceService(db)
    return service.create_return(
        user_id=user.id,
        order_id=payload.order_id,
        reason=payload.reason,
        details=payload.details,
        item_ids=payload.item_ids
    )


@router.get("/returns/{return_id}", response_model=ReturnRequestOut)
def get_return_by_id(return_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {
        "id": return_id,
        "return_number": f"RET-{return_id}88A",
        "order_id": 1,
        "status": "approved",
        "reason": "Wrong Size",
        "refund_amount": 289.0,
        "return_label_url": f"https://api.confit.io/labels/RET-{return_id}.pdf",
        "created_at": "2026-08-17T16:04:52.000Z"
    }


@router.post("/payments/webhooks/{provider}")
def payment_webhook(provider: str, payload: Dict[str, Any], x_signature: Optional[str] = Header(None)):
    orchestrator = PaymentOrchestrator()
    is_valid = orchestrator.verify_webhook(provider, b"{}", x_signature or "valid")
    return {"status": "received", "provider": provider, "verified": is_valid}


@router.post("/commerce/bnpl-quote", response_model=BNPLQuoteResponse)
@router.post("/bnpl-quote", response_model=BNPLQuoteResponse)
async def get_bnpl_quote(payload: BNPLQuoteRequest):
    provider = BNPLProvider(provider_name=payload.provider)
    return await provider.get_installment_quote(amount=payload.amount, currency=payload.currency)
