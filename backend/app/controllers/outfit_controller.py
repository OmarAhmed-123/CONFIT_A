from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user, get_current_user_optional
from backend.app.models.user import User
from backend.app.models.stylist import Outfit
from backend.app.services.outfit_service import (
    DEFAULT_SHARE_TTL_DAYS,
    OutfitCompositionError,
    OutfitService,
)
from backend.app.services.commerce_service import CommerceService
from backend.app.schemas.stylist import (
    CompositionPreviewInput,
    CompositionVerdictOut,
    OutfitCreateInput,
    OutfitItemsReplaceInput,
    OutfitOut,
    OutfitUpdateInput,
    ShareLinkOut,
    ShareRevokeOut,
    ShareRequestInput,
)

router = APIRouter(prefix="/outfits", tags=["Outfits & My Looks"])


def _get_owned_outfit(service: OutfitService, outfit_id: int, user: User) -> Outfit:
    """Fetch an outfit and enforce that the requesting user owns it.

    Server-side object-level authorization (IDOR fix): every read/mutation of a
    specific outfit verifies ownership. Non-existent and not-owned outfits are
    indistinguishable (404) to avoid leaking existence.
    """
    outfit = service.stylist_repo.get_outfit_by_id(outfit_id)
    if not outfit or outfit.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outfit not found")
    return outfit


def _composition_http_error(exc: OutfitCompositionError) -> HTTPException:
    """Turn a policy verdict into an explainable 422.

    The audit required that a rejected combination state its reason: the body
    carries machine-readable violation codes AND the offending slots, so the
    canvas can highlight them instead of showing a generic failure.
    """
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "message": exc.verdict.first_message,
            "code": "invalid_outfit_composition",
            **exc.verdict.to_dict(),
        },
    )


@router.get("", response_model=List[OutfitOut])
@router.get("/my-looks", response_model=List[OutfitOut])
def get_my_saved_looks(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Authenticated only — a guest must never receive another user's looks.
    service = OutfitService(db)
    return service.get_user_looks(user.id)


@router.post("", response_model=OutfitOut, status_code=status.HTTP_201_CREATED)
@router.post("/save", response_model=OutfitOut, status_code=status.HTTP_201_CREATED)
def save_custom_outfit(
    payload: OutfitCreateInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = OutfitService(db)
    if not payload.product_sku_ids and not payload.product_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide at least one of product_sku_ids or product_ids.",
        )
    try:
        outfit = service.save_outfit(
            user_id=user.id,
            title=payload.title,
            occasion=payload.occasion,
            product_sku_ids=payload.product_sku_ids or [],
            product_ids=payload.product_ids or [],
            description=payload.description,
        )
    except OutfitCompositionError as exc:
        raise _composition_http_error(exc)
    return service.get_outfit_payload(outfit.id, user.id)


@router.get("/{outfit_id}", response_model=OutfitOut)
def get_outfit_by_id(
    outfit_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = OutfitService(db)
    _get_owned_outfit(service, outfit_id, user)
    payload = service.get_outfit_payload(outfit_id, user.id)
    if not payload:
        raise HTTPException(status_code=404, detail="Outfit formatting error")
    return payload


@router.patch("/{outfit_id}", response_model=OutfitOut)
def patch_outfit_by_id(
    outfit_id: int,
    payload: OutfitUpdateInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = OutfitService(db)
    outfit = _get_owned_outfit(service, outfit_id, user)
    # Allow-listed updates only (typed schema prevents mass-assignment).
    if payload.title is not None:
        outfit.title = payload.title
    if payload.occasion is not None:
        outfit.occasion = payload.occasion
    if payload.description is not None:
        outfit.description = payload.description
    from backend.app.services.outfit_service import _utcnow
    outfit.updated_at = _utcnow()
    db.commit()
    return service.get_outfit_payload(outfit_id, user.id)


@router.delete("/{outfit_id}", status_code=status.HTTP_200_OK)
def delete_outfit_by_id(
    outfit_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = OutfitService(db)
    outfit = _get_owned_outfit(service, outfit_id, user)
    service.stylist_repo.delete_outfit(outfit.id)
    return {"status": "success", "outfit_id": outfit_id, "deleted": True}


@router.put("/{outfit_id}/items", response_model=OutfitOut)
def replace_outfit_items(
    outfit_id: int,
    payload: OutfitItemsReplaceInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Replace the whole item set of a saved look (canvas edit + reorder).

    The audit found saved looks were effectively immutable — only the title
    could change. This is the real edit path: ownership-checked, policy
    validated, and applied atomically so a rejected edit leaves the stored
    outfit exactly as it was.
    """
    service = OutfitService(db)
    outfit = _get_owned_outfit(service, outfit_id, user)
    if not payload.product_sku_ids and not payload.product_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide at least one of product_sku_ids or product_ids.",
        )
    try:
        service.replace_outfit_items(
            outfit,
            product_sku_ids=payload.product_sku_ids or [],
            product_ids=payload.product_ids or [],
        )
    except OutfitCompositionError as exc:
        raise _composition_http_error(exc)
    return service.get_outfit_payload(outfit_id, user.id)


@router.post("/composition/preview", response_model=CompositionVerdictOut)
def preview_composition(
    payload: CompositionPreviewInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Dry-run the composition rules for the live canvas.

    Same policy object as the write path (DRY), so the preview can never
    disagree with what Save will actually do.
    """
    service = OutfitService(db)
    return service.preview_composition(
        product_sku_ids=payload.product_sku_ids or [],
        product_ids=payload.product_ids or [],
    )


@router.post("/{outfit_id}/share", response_model=ShareLinkOut)
def share_outfit(
    outfit_id: int,
    payload: Optional[ShareRequestInput] = Body(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mint (or return the still-live) public share link for an owned outfit.

    Idempotent unless ``rotate=true``. The response always states the real
    expiry and active flag — the client never has to assume a link is live.
    """
    service = OutfitService(db)
    outfit = _get_owned_outfit(service, outfit_id, user)
    ttl = (payload.ttl_days if payload and payload.ttl_days else DEFAULT_SHARE_TTL_DAYS)
    rotate = bool(payload.rotate) if payload else False
    return service.mint_share_token(outfit, ttl_days=ttl, rotate=rotate)


@router.get("/{outfit_id}/share", response_model=ShareLinkOut)
def get_share_state(
    outfit_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Owner-facing share status: active?, expiry, real view count."""
    service = OutfitService(db)
    outfit = _get_owned_outfit(service, outfit_id, user)
    state = service.get_share_state(outfit)
    return {
        "outfit_id": state["outfit_id"],
        "share_token": state["share_token"],
        "share_url": state["share_url"],
        "expires_at": state["expires_at"],
        "is_active": state["is_active"],
        "view_count": state["view_count"],
    }


@router.delete("/{outfit_id}/share", response_model=ShareRevokeOut)
def revoke_share_link(
    outfit_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Revoke the public link. Idempotent; the token is never re-issued."""
    service = OutfitService(db)
    outfit = _get_owned_outfit(service, outfit_id, user)
    return service.revoke_share_token(outfit)


@router.post("/{outfit_id}/add-to-cart")
@router.post("/{outfit_id}/add-all-to-cart")
def add_outfit_to_cart(
    outfit_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = OutfitService(db)
    comm_service = CommerceService(db)
    outfit = _get_owned_outfit(service, outfit_id, user)

    cart = comm_service.commerce_repo.get_or_create_cart(f"user_{user.id}", user_id=user.id)
    added_count = 0
    for item in outfit.items:
        if item.product_sku_id:
            comm_service.commerce_repo.add_to_cart(cart.id, item.product_sku_id, quantity=1, outfit_id=outfit.id)
            added_count += 1

    return {
        "status": "success",
        "outfit_id": outfit.id,
        "items_added": added_count,
        "message": f"Added {added_count} items from look to cart."
    }
