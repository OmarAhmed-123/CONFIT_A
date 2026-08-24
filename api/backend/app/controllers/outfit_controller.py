import uuid
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user, get_current_user_optional
from backend.app.models.user import User
from backend.app.services.outfit_service import OutfitService
from backend.app.services.commerce_service import CommerceService
from backend.app.schemas.stylist import OutfitCreateInput, OutfitOut

router = APIRouter(prefix="/outfits", tags=["Outfits & My Looks"])


@router.get("", response_model=List[OutfitOut])
@router.get("/my-looks", response_model=List[OutfitOut])
def get_my_saved_looks(
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = OutfitService(db)
    user_id = user.id if user else 1
    return service.get_user_looks(user_id)


@router.post("", response_model=OutfitOut, status_code=status.HTTP_201_CREATED)
@router.post("/save", response_model=OutfitOut)
def save_custom_outfit(
    payload: OutfitCreateInput,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = OutfitService(db)
    user_id = user.id if user else 1
    outfit = service.save_outfit(
        user_id=user_id,
        title=payload.title,
        occasion=payload.occasion,
        product_sku_ids=payload.product_sku_ids,
        description=payload.description
    )
    all_looks = service.get_user_looks(user_id)
    return all_looks[0]


@router.get("/{outfit_id}", response_model=OutfitOut)
def get_outfit_by_id(
    outfit_id: int,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = OutfitService(db)
    outfit = service.stylist_repo.get_outfit_by_id(outfit_id)
    if not outfit:
        raise HTTPException(status_code=404, detail="Outfit not found")
    all_looks = service.get_user_looks(outfit.user_id or 1)
    for l in all_looks:
        if l["id"] == outfit_id:
            return l
    raise HTTPException(status_code=404, detail="Outfit formatting error")


@router.patch("/{outfit_id}", response_model=Dict[str, Any])
def patch_outfit_by_id(
    outfit_id: int,
    payload: Dict[str, Any],
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = OutfitService(db)
    outfit = service.stylist_repo.get_outfit_by_id(outfit_id)
    if not outfit:
        raise HTTPException(status_code=404, detail="Outfit not found")
    if "title" in payload:
        outfit.title = payload["title"]
    if "occasion" in payload:
        outfit.occasion = payload["occasion"]
    db.commit()
    return {"status": "success", "outfit_id": outfit_id, "updated": True}


@router.post("/{outfit_id}/share")
def share_outfit(outfit_id: int, user: Optional[User] = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    service = OutfitService(db)
    outfit = service.stylist_repo.get_outfit_by_id(outfit_id)
    if not outfit:
        raise HTTPException(status_code=404, detail="Outfit not found")
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
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = OutfitService(db)
    comm_service = CommerceService(db)
    outfit = service.stylist_repo.get_outfit_by_id(outfit_id)
    if not outfit:
        raise HTTPException(status_code=404, detail="Outfit not found")

    cart = comm_service.commerce_repo.get_or_create_cart("guest_session_outfit", user_id=user.id if user else None)
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
