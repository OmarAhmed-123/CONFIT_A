import uuid
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user
from backend.app.models.user import User
from backend.app.models.stylist import Outfit
from backend.app.services.outfit_service import OutfitService
from backend.app.services.commerce_service import CommerceService
from backend.app.schemas.stylist import OutfitCreateInput, OutfitOut

router = APIRouter(prefix="/outfits", tags=["Outfits & My Looks"])


def _get_owned_outfit(db: Session, user: User, outfit_id: int) -> Outfit:
    """Load an outfit and enforce that it belongs to the caller.

    Returns 404 (not 403) for both "doesn't exist" and "belongs to another
    user" so the endpoint is not an enumeration oracle for other people's
    outfit IDs. Group 1 §3: every user-owned outfit operation resolves the
    authenticated identity first, then verifies ownership, then acts.
    """
    service = OutfitService(db)
    outfit = service.stylist_repo.get_outfit_by_id(outfit_id)
    if not outfit or outfit.user_id != user.id:
        raise HTTPException(status_code=404, detail="Outfit not found")
    return outfit


@router.get("", response_model=List[OutfitOut])
@router.get("/my-looks", response_model=List[OutfitOut])
def get_my_saved_looks(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Saved looks are personal data — anonymous callers get 401, never the
    # previous "preview as user #1" fallback.
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
    service.save_outfit(
        user_id=user.id,
        title=payload.title,
        occasion=payload.occasion,
        product_sku_ids=payload.product_sku_ids,
        description=payload.description
    )
    # Return the newly saved look (most recent for this user).
    all_looks = service.get_user_looks(user.id)
    return all_looks[0]


@router.get("/{outfit_id}", response_model=OutfitOut)
def get_outfit_by_id(
    outfit_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    outfit = _get_owned_outfit(db, user, outfit_id)
    service = OutfitService(db)
    for look in service.get_user_looks(user.id):
        if look["id"] == outfit_id:
            return look
    raise HTTPException(status_code=404, detail="Outfit formatting error")


@router.patch("/{outfit_id}", response_model=Dict[str, Any])
def patch_outfit_by_id(
    outfit_id: int,
    payload: Dict[str, Any],
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    outfit = _get_owned_outfit(db, user, outfit_id)
    if "title" in payload:
        outfit.title = payload["title"]
    if "occasion" in payload:
        outfit.occasion = payload["occasion"]
    if "description" in payload:
        outfit.description = payload["description"]
    db.commit()
    return {"status": "success", "outfit_id": outfit_id, "updated": True}


@router.delete("/{outfit_id}")
def delete_outfit(
    outfit_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    outfit = _get_owned_outfit(db, user, outfit_id)
    db.delete(outfit)
    db.commit()
    return {"status": "success", "outfit_id": outfit_id, "deleted": True}


@router.post("/{outfit_id}/share")
def share_outfit(
    outfit_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    outfit = _get_owned_outfit(db, user, outfit_id)
    share_token = outfit.share_token or f"look_{uuid.uuid4().hex[:8]}"
    outfit.share_token = share_token
    db.commit()
    return {
        "outfit_id": outfit.id,
        "share_token": share_token,
        "share_url": f"https://confit.io/looks/{share_token}",
        "card_image_url": f"https://api.confit.io/cards/{share_token}.png"
    }


@router.post("/{outfit_id}/add-to-cart")
@router.post("/{outfit_id}/add-all-to-cart")
def add_outfit_to_cart(
    outfit_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    outfit = _get_owned_outfit(db, user, outfit_id)
    comm_service = CommerceService(db)
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
