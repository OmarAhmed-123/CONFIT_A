from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user, get_current_user_optional
from backend.app.models.user import User
from backend.app.services.wardrobe_service import WardrobeService
from backend.app.services.gap_analysis_service import GapAnalysisService, DuplicateDetectorService
from backend.app.schemas.wardrobe import (
    WardrobeItemCreate,
    WardrobeItemUpdate,
    WardrobeItemOut,
    WardrobeAutoTagRequest,
    GapAnalysisOut,
    DuplicateCheckRequest,
    DuplicateAlertResponse,
    WardrobeUploadResponse,
    WardrobeFirstOutfitOut,
)

router = APIRouter(prefix="/wardrobe", tags=["Virtual Wardrobe & Smart Reuse"])


@router.get("/items", response_model=List[WardrobeItemOut])
def get_my_wardrobe(
    category: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Group 1 §2: the wardrobe is user-owned data. Anonymous callers get
    # 401 — there is no "preview as user #1" fallback leaking a real
    # account's items to guests.
    service = WardrobeService(db)
    return service.get_user_wardrobe(user.id, category)


@router.post("/items", response_model=WardrobeItemOut, status_code=status.HTTP_201_CREATED)
def add_wardrobe_item(
    payload: WardrobeItemCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = WardrobeService(db)
    return service.add_item(user.id, payload.model_dump())


@router.get("/items/{item_id}", response_model=WardrobeItemOut)
def get_single_wardrobe_item(
    item_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # get_item_by_id scopes the query to the authenticated user's id, so a
    # cross-user IDOR attempt resolves to "not found" (404) rather than
    # confirming the item exists (403) — no resource-enumeration oracle.
    service = WardrobeService(db)
    item = service.wardrobe_repo.get_item_by_id(item_id, user.id)
    if not item:
        raise HTTPException(status_code=404, detail="Wardrobe item not found")
    return service._to_dict(item)


@router.put("/items/{item_id}", response_model=WardrobeItemOut)
@router.patch("/items/{item_id}", response_model=WardrobeItemOut)
def update_wardrobe_item(
    item_id: int,
    payload: WardrobeItemUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = WardrobeService(db)
    return service.update_item(user.id, item_id, payload.model_dump(exclude_unset=True))


@router.delete("/items/{item_id}")
def delete_wardrobe_item(
    item_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    service = WardrobeService(db)
    service.delete_item(user.id, item_id)
    return {"status": "success", "message": "Item deleted from wardrobe."}


@router.post("/upload", response_model=WardrobeUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_wardrobe_image(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Single-image wardrobe upload: validate -> store -> AI analyze -> persist.

    The item row is created before analysis so an AI failure still leaves the
    user's photo safely stored with status 'failed' (retryable) — never a
    fake 'ready' item with invented tags.
    """
    data = await file.read()
    service = WardrobeService(db)
    result = await service.upload_items(user.id, [(file.filename or "upload", file.content_type, data)])
    entry = result["results"][0]
    if entry["status"] == "failed":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=entry["detail"])
    return result


@router.post("/upload/bulk", response_model=WardrobeUploadResponse, status_code=status.HTTP_201_CREATED)
async def bulk_upload_wardrobe_images(
    files: List[UploadFile] = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Bulk import with per-item isolation: partial success is returned with
    a per-file status so the UI can show exactly which item failed (BRD §13)."""
    if not files:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No files provided.")
    if len(files) > 20:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Bulk import is limited to 20 files per batch.")
    payload = []
    for f in files:
        payload.append((f.filename or "upload", f.content_type, await f.read()))
    service = WardrobeService(db)
    return await service.upload_items(user.id, payload)


@router.post("/items/{item_id}/analyze", response_model=WardrobeItemOut)
async def analyze_wardrobe_item(item_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """(Re)run AI analysis on an owned item — the retry path for failed items.
    Ownership is enforced in the service; another user's item resolves to 404."""
    service = WardrobeService(db)
    return await service.analyze_item(user.id, item_id)


@router.post("/auto-tag")
async def auto_tag_item(
    payload: WardrobeAutoTagRequest,
    db: Session = Depends(get_db)
):
    """Upload-form preview tagging via the real vision provider. When no
    vision model is configured the response honestly reports
    analysis_available=false instead of returning fabricated attributes."""
    service = WardrobeService(db)
    return await service.auto_tag_image(payload.image_url, payload.image_base64)


@router.get("/outfit-suggestions", response_model=WardrobeFirstOutfitOut)
def wardrobe_first_outfit(
    occasion: str = Query("Smart Casual"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Group 4 §24 'shop your wardrobe first': build a look from the caller's
    owned pieces via the existing outfit/styling engine; only positions the
    wardrobe cannot fill become purchasable catalog suggestions."""
    from backend.app.services.outfit_service import OutfitService
    service = OutfitService(db)
    return service.build_wardrobe_first_outfit(user.id, occasion=occasion)


@router.get("/gap-analysis", response_model=List[GapAnalysisOut])
@router.post("/gap-analysis", response_model=List[GapAnalysisOut])
def get_wardrobe_gap_analysis(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Gap analysis reads the caller's wardrobe — user-owned data, so it
    # requires authentication and never falls back to a default account.
    service = GapAnalysisService(db)
    return service.analyze_wardrobe_gaps(user.id)


@router.post("/duplicate-check", response_model=DuplicateAlertResponse)
@router.post("/check-duplicate", response_model=DuplicateAlertResponse)
def check_duplicate_purchase(
    payload: DuplicateCheckRequest,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    # Anonymous duplicate-check is safe: it returns a constant "no risk"
    # response WITHOUT touching any user's wardrobe (no data leak). Only an
    # authenticated caller's own wardrobe is ever queried.
    if not user:
        return DuplicateAlertResponse(
            has_duplicate_risk=False,
            similarity_score=0,
            owned_item=None,
            alert_message=None,
            comparison_notes=None
        )
    service = DuplicateDetectorService(db)
    return service.check_duplicate(
        user_id=user.id,
        product_id=payload.product_id,
        product_title=payload.product_title,
        category=payload.category,
        color_family=payload.color_family,
        strict_mode=payload.strict_mode,
        pattern=payload.pattern
    )
