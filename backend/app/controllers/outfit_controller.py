import secrets
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user, get_current_user_optional
from backend.app.models.user import User
from backend.app.models.stylist import Outfit
from backend.app.services.outfit_service import OutfitService
from backend.app.services.commerce_service import CommerceService
from backend.app.schemas.stylist import OutfitCreateInput, OutfitUpdateInput, OutfitOut

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
    outfit = service.save_outfit(
        user_id=user.id,
        title=payload.title,
        occasion=payload.occasion,
        product_sku_ids=payload.product_sku_ids or [],
        product_ids=payload.product_ids or [],
        description=payload.description,
    )
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


@router.post("/{outfit_id}/share")
def share_outfit(
    outfit_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = OutfitService(db)
    outfit = _get_owned_outfit(service, outfit_id, user)
    # C8: cryptographically strong, non-sequential, non-predictable token
    # (~192 bits of entropy, URL-safe, never truncated). Uniqueness is
    # enforced by the unique column + retry on the (astronomically unlikely)
    # collision.
    share_token = outfit.share_token
    if not share_token:
        share_token = f"look_{secrets.token_urlsafe(24)}"
        while service.stylist_repo.get_outfit_by_share_token(share_token):
            share_token = f"look_{secrets.token_urlsafe(24)}"
        outfit.share_token = share_token
        db.commit()
    # share_url is a relative frontend route served by this application's own
    # SPA (/looks/:token) — no fabricated external domain, and no fake
    # server-rendered card URL: PNG cards are generated client-side (C7).
    return {
        "outfit_id": outfit.id,
        "share_token": share_token,
        "share_url": f"/looks/{share_token}",
    }


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
