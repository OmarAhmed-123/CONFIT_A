import base64
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from limits import parse as parse_rate_limit
from sqlalchemy.orm import Session
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user_optional, get_presentation_currency
from backend.app.services.pricing_presentation import PresentationCurrency, present
from backend.app.core.rate_limit import client_key, limiter
from backend.app.models.user import User
from backend.app.services.content_safety_service import (
    content_safety_service,
    refusal_for,
)
from backend.app.services.stylist_image_intake import ImageIntakeError, ParsedImage, parse_images
from backend.app.services.stylist_service import StylistService
from backend.app.services.outfit_service import OutfitService
from backend.app.schemas.stylist import (
    StylistPromptRequest,
    StylistMessageOut,
    CompatibilityCheckRequest,
    CompatibilityCheckResponse
)

router = APIRouter(prefix="/stylist", tags=["AI Virtual Stylist & Styling Engine"])


def _enforce_image_budget(request: Request) -> None:
    """Per-caller budget for image-carrying turns (STY-08 / FR-009).

    Image turns cost a vision call on top of the text call, so they get their own,
    tighter bucket than text turns. The counter lives in the shared limiter store,
    so it follows the same honesty rules as the other AI limits: in-process on a
    single instance unless a shared store is configured (see core/rate_limit.py).
    """
    if not limiter.enabled:
        return
    key = f"stylist-image-turns:{client_key(request)}"
    allowed = limiter._limiter.hit(
        parse_rate_limit(f"{settings.STYLIST_IMAGE_TURNS_PER_HOUR}/hour"), key
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "You have reached the limit for styling with photos this hour. "
                "Text styling is still available."
            ),
        )


async def _require_safe_images(images: List[ParsedImage]) -> None:
    """Moderate every attached image before it is analysed. Fail closed.

    Same policy as the wardrobe upload gate (block before anything is processed),
    and the same single exception: a deployment with no NVIDIA credentials cannot
    screen, so the gate stands down visibly (no vision analysis runs there either).
    """
    if not content_safety_service.configured:
        return
    for image in images:
        data_uri = f"data:{image.mime};base64,{base64.b64encode(image.data).decode('ascii')}"
        verdict = await content_safety_service.check_image(data_uri, context="stylist_upload")
        if not verdict.measured:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Image safety screening is temporarily unavailable, so the photo "
                    "was not analysed. Please try again shortly."
                ),
            )
        if verdict.should_block:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=refusal_for(verdict, is_image=True),
            )


@router.post("/chat", response_model=StylistMessageOut)
# Threat: every call spends provider quota (and writes a stylist message row),
# and the endpoint accepts anonymous callers, so without a limit it is a free
# LLM proxy keyed to this deployment's credentials. Cost control, per caller.
# Measured 2026-09-23: this was the only AI-costing endpoint with no limit at
# all, while /try-on/* (GPU) and /auth/* (brute force) already had them.
@limiter.limit("20/hour")
async def chat_with_stylist(
    request: Request,
    payload: StylistPromptRequest,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
    fx: PresentationCurrency = Depends(get_presentation_currency),
):
    service = StylistService(db)
    user_id = user.id if user else None
    # Mode A: validate (at the schema boundary, already done), budget, screen,
    # then decode. A refused image never reaches the service, so nothing is
    # persisted for it.
    images: List[ParsedImage] = []
    if payload.images:
        _enforce_image_budget(request)
        try:
            images = parse_images(payload.images)
        except ImageIntakeError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
        await _require_safe_images(images)
    # Money honesty (C05). The stylist was the ONE read path outside the
    # presentation-currency system: it quoted raw price-book amounts (USD)
    # while every other surface the shopper sees is converted (EGP). Same
    # contract as the catalog: the budget arrives in the DISPLAYED currency
    # and is converted to the price book before the engine compares it
    # (PresentationCurrency.to_pricing); the response is converted back with
    # the shared `present` walker, which restamps item/outfit currency labels.
    try:
        result = await _interact(service, user_id, payload, fx, images)
    except ImageIntakeError as exc:
        # Raised by the service BEFORE any row is written (an unreadable picture).
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return present(result, fx)


async def _interact(service, user_id, payload, fx, images):
    return await service.interact_with_stylist(
        user_id=user_id,
        prompt=payload.prompt,
        session_id=payload.session_id,
        occasion=payload.occasion,
        budget_limit=fx.to_pricing(payload.budget_limit),
        voice_input_used=payload.voice_input_used,
        recommendation_constraints=(payload.recommendation_constraints.model_dump(exclude_none=True) if payload.recommendation_constraints else None),
        images=images,
        include_wardrobe_items=payload.include_wardrobe_items,
        history=[{"role": t.role, "content": t.content} for t in (payload.history or [])],
    )


@router.post("/compatibility", response_model=CompatibilityCheckResponse)
async def check_outfit_compatibility(
    payload: CompatibilityCheckRequest,
    db: Session = Depends(get_db)
):
    service = OutfitService(db)
    # Feature 06: the real OutfitTransformer model scores the set when the
    # worker is configured; the deterministic rules heuristic answers
    # otherwise. The response names which engine produced the score.
    return await service.evaluate_compatibility(
        product_ids=payload.product_ids,
        target_occasion=payload.target_occasion or "Casual"
    )
