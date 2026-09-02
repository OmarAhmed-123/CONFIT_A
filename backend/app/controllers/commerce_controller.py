import os
import re
import json
import uuid
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user_optional, get_current_user
from backend.app.models.user import User
from backend.app.services.commerce_service import CommerceService
from backend.app.providers.bnpl_provider import BNPLProvider
from backend.app.providers.payment.orchestrator import PaymentOrchestrator
from backend.app.providers.payment.schemas import MarketPaymentCapabilitiesResponse
from backend.app.schemas.commerce import (
    CartOut,
    CartItemAdd,
    CartItemQuantityUpdate,
    PromoApplyRequest,
    CheckoutRequest,
    OrderOut,
    OrderTrackingTimelineOut,
    ReturnRequestCreate,
    ReturnRequestOut,
    ExchangeCreate,
    ExchangeOut,
    BNPLQuoteRequest,
    BNPLQuoteResponse
)
from backend.app.core.exceptions import ResourceNotFoundError, ValidationDomainError
from pydantic import BaseModel

router = APIRouter(tags=["Commerce, Payments & Fulfillment"])


class CartMergeRequest(BaseModel):
    guest_token: str


@router.get("/payments/methods", response_model=MarketPaymentCapabilitiesResponse)
@router.get("/commerce/payment-methods", response_model=MarketPaymentCapabilitiesResponse)
def get_payment_methods_for_market(
    country_code: Optional[str] = Query("EG", description="Country code e.g. 'EG', 'AE', 'SA', 'QA', 'KW'")
):
    orchestrator = PaymentOrchestrator()
    return orchestrator.get_market_methods(country_code or "EG")


@router.get("/commerce/cart", response_model=CartOut)
@router.get("/cart", response_model=CartOut)
def get_cart(
    x_session_token: str = Header(...),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = CommerceService(db)
    return service.get_cart(x_session_token, user_id=user.id if user else None)


@router.post("/commerce/cart/items", response_model=CartOut, status_code=status.HTTP_201_CREATED)
@router.post("/cart/items", response_model=CartOut, status_code=status.HTTP_201_CREATED)
def add_to_cart(
    payload: CartItemAdd,
    x_session_token: str = Header(...),
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
    payload: CartItemQuantityUpdate,
    x_session_token: str = Header(...),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = CommerceService(db)
    return service.update_quantity(
        x_session_token, item_id, payload.quantity, user_id=user.id if user else None
    )


@router.delete("/commerce/cart/items/{item_id}", response_model=CartOut)
@router.delete("/cart/items/{item_id}", response_model=CartOut)
def remove_from_cart(
    item_id: int,
    x_session_token: str = Header(...),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = CommerceService(db)
    return service.remove_item(x_session_token, item_id, user_id=user.id if user else None)


@router.post("/commerce/cart/promo", response_model=CartOut)
@router.post("/cart/promo", response_model=CartOut)
def apply_promo(
    payload: PromoApplyRequest,
    x_session_token: str = Header(...),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = CommerceService(db)
    return service.apply_promo(
        x_session_token, payload.promo_code, user_id=user.id if user else None
    )


@router.post("/cart/merge", response_model=CartOut)
def merge_guest_cart(
    payload: CartMergeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = CommerceService(db)
    return service.merge_guest_cart(payload.guest_token, user.id)


@router.post("/commerce/checkout", response_model=OrderOut)
@router.post("/checkout", response_model=OrderOut)
async def checkout_order(
    payload: CheckoutRequest,
    x_session_token: str = Header(...),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = CommerceService(db)
    return await service.checkout(
        session_token=x_session_token,
        checkout_data=payload.model_dump(),
        user_id=user.id if user else None,
    )


# DEPRECATED: checkout/sessions endpoints were dead code (token generated but never persisted,
# get always 404). Frontend uses direct POST /commerce/checkout with idempotency_key.
# These endpoints now return honest 501 to prevent confusion. If session-based checkout
# is needed in future, implement CheckoutSession table + Alembic migration 0009.

@router.post("/checkout/sessions", include_in_schema=False)
def create_checkout_session_deprecated():
    from fastapi import HTTPException
    raise HTTPException(
        status_code=501,
        detail={
            "code": "FEATURE_NOT_IMPLEMENTED",
            "message": "Checkout sessions are not implemented. Use POST /commerce/checkout with idempotency_key directly. See CheckoutView.tsx",
            "hint": "Direct checkout is the canonical flow - see commerceService.checkout()"
        }
    )


@router.get("/checkout/sessions/{token}", include_in_schema=False)
def get_checkout_session_deprecated(token: str):
    from fastapi import HTTPException
    raise HTTPException(
        status_code=501,
        detail={
            "code": "FEATURE_NOT_IMPLEMENTED",
            "message": f"Checkout session {token} lookup not implemented. Use direct checkout.",
        }
    )


@router.post("/checkout/sessions/{token}/confirm", include_in_schema=False)
async def confirm_checkout_session_deprecated(token: str):
    from fastapi import HTTPException
    raise HTTPException(
        status_code=501,
        detail={
            "code": "FEATURE_NOT_IMPLEMENTED",
            "message": f"Checkout session {token} confirm not implemented. Use POST /commerce/checkout",
        }
    )


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
    service.assert_order_access(order, user)
    return order


@router.get("/commerce/orders/{order_number}/tracking", response_model=OrderTrackingTimelineOut)
@router.get("/orders/{order_number}/tracking", response_model=OrderTrackingTimelineOut)
def get_order_tracking_timeline(order_number: str, db: Session = Depends(get_db)):
    service = CommerceService(db)
    return service.get_order_tracking(order_number)


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


@router.get("/returns/labels/{ref}")
def download_return_label(ref: str):
    if not re.fullmatch(r"RA-[A-Z0-9]{6,16}", ref):
        raise ResourceNotFoundError("ReturnLabel", ref)
    path = os.path.join(settings.STORAGE_LOCAL_DIR, "return-labels", f"{ref}.txt")
    if not os.path.isfile(path):
        raise ResourceNotFoundError("ReturnLabel", ref)
    return FileResponse(path, media_type="text/plain", filename=f"{ref}.txt")


@router.get("/returns/{return_id}", response_model=ReturnRequestOut)
def get_return_by_id(return_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    service = CommerceService(db)
    return service.get_return(return_id, user.id)


@router.post("/commerce/returns/{return_id}/refund", response_model=ReturnRequestOut)
async def refund_return(
    return_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = CommerceService(db)
    service.get_return(return_id, user.id)
    return await service.refund_return(return_id)


@router.post("/commerce/exchanges", response_model=ExchangeOut, status_code=status.HTTP_201_CREATED)
@router.post("/exchanges", response_model=ExchangeOut, status_code=status.HTTP_201_CREATED)
async def create_exchange(
    payload: ExchangeCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = CommerceService(db)
    return await service.create_exchange(
        user_id=user.id,
        order_id=payload.order_id,
        original_item_id=payload.original_item_id,
        replacement_sku_id=payload.replacement_sku_id,
    )


@router.post("/payments/webhooks/{provider}")
async def payment_webhook(
    request: Request,
    provider: str,
    db: Session = Depends(get_db),
    x_signature: Optional[str] = Header(None),
):
    """PSP webhook intake. Signature is verified over the RAW request body."""
    raw_body = await request.body()
    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}
    service = CommerceService(db)
    return await service.process_webhook(provider, payload, raw_body, x_signature or "")


@router.post("/commerce/bnpl-quote", response_model=BNPLQuoteResponse)
@router.post("/bnpl-quote", response_model=BNPLQuoteResponse)
async def get_bnpl_quote(payload: BNPLQuoteRequest):
    provider = BNPLProvider(provider_name=payload.provider)
    return await provider.get_installment_quote(amount=payload.amount, currency=payload.currency)
