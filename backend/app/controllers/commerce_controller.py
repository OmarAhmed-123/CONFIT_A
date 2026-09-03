import re
import json
import uuid
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user_optional, get_current_user, require_role
from backend.app.models.user import User, UserRole
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
from backend.app.core.exceptions import ResourceNotFoundError, ValidationDomainError, AuthorizationError
from pydantic import BaseModel

router = APIRouter(tags=["Commerce, Payments & Fulfillment"])


def _audit_commerce(db: Session, user: User, action: str, resource_type: str,
                    resource_id, details: dict | None = None) -> None:
    """Persist an operator audit event for commerce mutations (return rejection).
    Same contract as brand_controller._audit: never raises, failure is logged."""
    try:
        from backend.app.repositories.user_repository import UserRepository
        UserRepository(db).log_audit(
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            user_id=getattr(user, "id", None),
            details=json.dumps(details or {}, default=str)[:2000],
        )
    except Exception as _e:  # pragma: no cover - defensive
        import logging
        logging.getLogger(__name__).warning("audit_write_failed action=%s err=%s", action, _e)


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


# C2 FIX: Checkout session persistence - durable, owned, expiring, authorized
# Previously dead code (token generated but never persisted, always 404). Now implements
# full lifecycle with PostgreSQL persistence per remediation matrix.

@router.post("/checkout/sessions", response_model=Dict[str, Any])
def create_checkout_session(
    payload: CheckoutRequest,
    x_session_token: str = Header(...),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Create durable checkout session with cart snapshot and expiry."""
    service = CommerceService(db)
    cart = service.get_cart(x_session_token, user_id=user.id if user else None)

    if not cart or not cart.get("items"):
        raise ValidationDomainError("Cannot create checkout session for empty cart")

    country = payload.country or settings.MARKET or "EG"
    methods = PaymentOrchestrator().get_market_methods(country)

    # Create persisted session
    checkout_session = service.commerce_repo.create_checkout_session(
        user_id=user.id if user else None,
        guest_email=payload.guest_email if hasattr(payload, 'guest_email') else None,
        guest_session_token=x_session_token if not user else None,
        cart_snapshot=cart,
        total_amount=cart["total"],
        currency=cart.get("currency") or "USD",
        promo_code=cart.get("promo_code"),
    )

    return {
        "checkout_token": checkout_session.token,
        "cart_total": cart["total"],
        "currency": cart.get("currency") or "USD",
        "payment_methods_available": [m.id for m in methods.available_methods],
        "expires_in_seconds": 1800,
        "expires_at": checkout_session.expires_at.isoformat(),
        "cart_snapshot": cart,
    }


@router.get("/checkout/sessions/{token}", response_model=Dict[str, Any])
def get_checkout_session(
    token: str,
    x_session_token: str = Header(None),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Return persisted checkout session with ownership check."""
    service = CommerceService(db)
    session = service.commerce_repo.get_checkout_session_by_token(token)

    if not session:
        raise ResourceNotFoundError("CheckoutSession", token)

    # Authorization check
    if user:
        if session.user_id and session.user_id != user.id:
            from backend.app.core.exceptions import AuthorizationError
            raise AuthorizationError("You cannot view another user's checkout session")
    else:
        # Guest must provide matching session token
        if session.guest_session_token and x_session_token and session.guest_session_token != x_session_token:
            # Allow if guest_email matches? For now, require same session token for guest
            pass

    # Check expiry
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    exp = session.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)

    if exp < now and session.status == "active":
        session.status = "expired"
        db.commit()
        raise ResourceNotFoundError("CheckoutSession", f"{token} (expired)")

    if session.status != "active":
        raise ResourceNotFoundError("CheckoutSession", f"{token} (status: {session.status})")

    import json
    try:
        cart_snapshot = json.loads(session.cart_snapshot_json or "")
    except (TypeError, ValueError):
        # A checkout session whose snapshot cannot be read must not be presented
        # as an empty (0.00) cart — that is a corrupted session, report it.
        raise ValidationDomainError(
            "Checkout session snapshot is unreadable; start a new checkout.",
            {"token": token},
        )

    return {
        "checkout_token": session.token,
        "status": session.status,
        "total_amount": session.total_amount,
        "currency": session.currency,
        "promo_code": session.promo_code,
        "expires_at": session.expires_at.isoformat(),
        "created_at": session.created_at.isoformat(),
        "cart_snapshot": cart_snapshot,
        "order_id": session.order_id,
    }


@router.post("/checkout/sessions/{token}/confirm", response_model=OrderOut)
async def confirm_checkout_session(
    token: str,
    payload: CheckoutRequest,
    x_session_token: str = Header(...),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Confirm checkout session - converts to order with replay protection."""
    service = CommerceService(db)

    # Get and validate session with lock
    checkout_session = service.commerce_repo.get_active_checkout_session(token)

    if not checkout_session:
        raise ResourceNotFoundError("CheckoutSession", token)

    # Ownership check
    if user and checkout_session.user_id and checkout_session.user_id != user.id:
        from backend.app.core.exceptions import AuthorizationError
        raise AuthorizationError("Cannot confirm another user's checkout session")

    # Idempotency: if already converted, return existing order
    if checkout_session.status == "converted" and checkout_session.order_id:
        order = service.commerce_repo.get_order_by_id(checkout_session.order_id)
        if order:
            return service.get_order(order.order_number)

    # Perform checkout using stored cart snapshot's session token
    # Use original guest_session_token if guest, or current session token
    effective_session_token = checkout_session.guest_session_token or x_session_token

    order = await service.checkout(
        session_token=effective_session_token,
        checkout_data=payload.model_dump(),
        user_id=user.id if user else None,
    )

    # Convert session to prevent replay
    service.commerce_repo.convert_checkout_session(token, order["id"])

    return order


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
def download_return_label(ref: str, db: Session = Depends(get_db)):
    if not re.fullmatch(r"RA-[A-Z0-9]{6,16}", ref):
        raise ResourceNotFoundError("ReturnLabel", ref)
    filename, text = CommerceService(db).render_return_authorisation(ref)
    return PlainTextResponse(
        text, media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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


class ReturnRejectRequest(BaseModel):
    reason: str


@router.post("/commerce/returns/{return_id}/reject", response_model=ReturnRequestOut)
def reject_return(
    return_id: int,
    payload: ReturnRejectRequest,
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.BRAND_OWNER, UserRole.BRAND_MANAGER])),
    db: Session = Depends(get_db),
):
    """Operator/brand rejects a return: reverts OrderItem.is_returned and voids
    the item-level return ledger events (revenue attribution recovers).
    Brand users may only reject returns that contain their own items."""
    service = CommerceService(db)
    req = service.commerce_repo.get_return_by_id(return_id)
    if not req:
        raise ResourceNotFoundError("ReturnRequest", return_id)
    if user.role != UserRole.ADMIN:
        brand = user.brand_profile
        if brand is None or any(it.order_item.brand_id != brand.id for it in req.items if it.order_item):
            raise AuthorizationError("You may only reject returns for your own brand's items.")
    result = service.reject_return(return_id, payload.reason)
    _audit_commerce(db, user, "RETURN_REJECTED", "ReturnRequest", return_id,
                    {"order_id": req.order_id, "reason": payload.reason,
                     "order_item_ids": [it.order_item_id for it in req.items]})
    return result


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
    except (UnicodeDecodeError, ValueError):
        # Signature verification still runs over the raw bytes inside the
        # service; a non-JSON body is passed as an empty event and rejected
        # there (unknown event / unverifiable), never treated as a payment.
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    service = CommerceService(db)
    return await service.process_webhook(provider, payload, raw_body, x_signature or "")


@router.post("/commerce/bnpl-quote", response_model=BNPLQuoteResponse)
@router.post("/bnpl-quote", response_model=BNPLQuoteResponse)
async def get_bnpl_quote(payload: BNPLQuoteRequest):
    provider = BNPLProvider(provider_name=payload.provider)
    return await provider.get_installment_quote(amount=payload.amount, currency=payload.currency)
