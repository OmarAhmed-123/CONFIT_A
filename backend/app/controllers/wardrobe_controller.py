from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status, UploadFile, File, Request
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.rate_limit import limiter
from backend.app.core.dependencies import get_current_user, get_current_user_optional
from backend.app.models.user import User
from backend.app.services.wardrobe_service import WardrobeService
from backend.app.services.content_safety_service import (
    ContentSafetyService,
    content_safety_service,
    refusal_for,
)
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


async def _require_safe_image(
    blob: bytes,
    content_type: Optional[str],
    *,
    user_id: int,
    service: ContentSafetyService = content_safety_service,
) -> None:
    """Moderate raw upload bytes, or refuse the upload.

    FAIL-CLOSED by design. The policy's S4 categories (body imagery of minors,
    non-consensual imagery) carry "block, do not persist" — a rule that can only
    be honoured before the bytes reach object storage, and one that an
    unreachable classifier must not be able to bypass. A rejected upload costs
    the user one retry; a stored illegal image is unrecoverable.

    The single exception is a deployment with no NVIDIA credentials at all:
    that is a legitimate configuration (self-hosted, air-gapped, local dev), not
    a failure, so the gate stands down rather than bricking every upload. It is
    visible in /health via the provider status rather than hidden here.
    """
    if not service.configured:
        return

    import base64

    from backend.app.services.wardrobe_service import ALLOWED_IMAGE_TYPES

    mime = (content_type or "").split(";")[0].strip().lower()
    if mime not in ALLOWED_IMAGE_TYPES:
        # Cheap, deterministic validation runs FIRST. An unsupported type is
        # rejected by WardrobeService._validate_image with the precise error the
        # API contract promises; moderating it here would both waste a model
        # call on bytes that can never be stored and replace that specific
        # 422 with a generic safety refusal.
        return
    data_uri = f"data:{mime};base64,{base64.b64encode(blob).decode('ascii')}"
    verdict = await service.check_image(data_uri, context="wardrobe_upload")

    if not verdict.measured:
        # Classifier configured but unreachable -> refuse. 503, not 422: the
        # user did nothing wrong and the request is retryable.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Image safety screening is temporarily unavailable, so the "
                "upload was not saved. Please try again shortly."
            ),
        )

    if verdict.should_block:
        # Never echo the category back: it accuses the user and leaks how the
        # classifier behaves (policy, Refusal guidance).
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=refusal_for(verdict, is_image=True),
        )



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
    # Housekeeping on the owner's own read: this deployment is serverless and
    # has no scheduler, so the bin is bounded here rather than by a cron that
    # does not exist. Never raises; a failed purge must not break a list.
    service._purge_expired_bin(user.id)
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
    permanent: bool = Query(
        False,
        description=(
            "Irreversible. Removes the row AND the stored photograph. The "
            "client must obtain explicit user confirmation before setting it."
        ),
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a wardrobe item — reversibly by default.

    The default moves the item to a bin and returns the undo contract:
    `restorable_until` (a real deadline the UI can render instead of guessing)
    and `restore_endpoint`. The stored photograph is kept for the window, so a
    restore returns the actual image and not a broken thumbnail.

    `?permanent=true` is the explicitly-confirmed destructive path. It is a
    separate parameter rather than a separate default so that a client which
    has not been updated keeps the SAFE behaviour: an old build that forgets
    the flag bins the item, it does not destroy it.
    """
    service = WardrobeService(db)
    if permanent:
        result = service.purge_item(user.id, item_id)
        return {
            "status": "success",
            "permanent": True,
            "undoable": False,
            "message": "Item permanently deleted.",
            **result,
        }
    result = service.delete_item(user.id, item_id)
    return {
        "status": "success",
        "permanent": False,
        "undoable": True,
        "message": "Item moved to the bin.",
        **result,
    }


@router.post("/items/{item_id}/restore")
def restore_wardrobe_item(
    item_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Undo a reversible delete.

    404 when the grace window has passed or the item was permanently
    deleted — the UI must be able to tell the user their Undo did not work.
    An Undo that reports success without restoring anything is worse than no
    Undo at all.

    Clicking Undo twice, or two tabs racing, returns success: the item is
    live, which is what the user asked for.
    """
    service = WardrobeService(db)
    return service.restore_item(user.id, item_id)


@router.post("/upload", response_model=WardrobeUploadResponse, status_code=status.HTTP_201_CREATED)
# Threat: each upload writes to object storage AND runs a vision model on
# consumer-provided bytes — both cost money, and consumer bytes are the classic
# abuse surface (upload abuse). Bounded per caller; the size/type validation in
# WardrobeService is a separate control and stays.
@limiter.limit("30/hour")
async def upload_wardrobe_image(
    request: Request,
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

    # Moderation gate — runs BEFORE storage on purpose. The S4 rule in
    # docs/safety/confit_safety_policy_v1.0.0.md is "block, do not persist":
    # once bytes reach the object store, a hard-block outcome is no longer
    # achievable. Fails CLOSED (see _require_safe_image).
    await _require_safe_image(data, file.content_type, user_id=user.id)

    service = WardrobeService(db)
    result = await service.upload_items(user.id, [(file.filename or "upload", file.content_type, data)])
    entry = result["results"][0]
    if entry["status"] == "failed":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=entry["detail"])
    return result


@router.post("/upload/bulk", response_model=WardrobeUploadResponse, status_code=status.HTTP_201_CREATED)
# Bulk multiplies the per-upload cost, so it gets its own, tighter bucket.
@limiter.limit("10/hour")
async def bulk_upload_wardrobe_images(
    request: Request,
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
        blob = await f.read()
        # Every file is gated individually — a batch must not become a way to
        # smuggle one unmoderated image past the single-upload guard.
        await _require_safe_image(blob, f.content_type, user_id=user.id)
        payload.append((f.filename or "upload", f.content_type, blob))
    service = WardrobeService(db)
    return await service.upload_items(user.id, payload)


@router.post("/items/{item_id}/analyze", response_model=WardrobeItemOut)
# Vision-model cost on a retry path: a client looping on a failing item would
# otherwise spend unbounded provider quota.
@limiter.limit("30/hour")
async def analyze_wardrobe_item(request: Request, item_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """(Re)run AI analysis on an owned item — the retry path for failed items.
    Ownership is enforced in the service; another user's item resolves to 404."""
    service = WardrobeService(db)
    return await service.analyze_item(user.id, item_id)


@router.post("/auto-tag")
# Unauthenticated vision call (upload-form preview): the only AI endpoint a
# guest can reach, so it needs the limit most.
@limiter.limit("30/hour")
async def auto_tag_item(
    request: Request,
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
