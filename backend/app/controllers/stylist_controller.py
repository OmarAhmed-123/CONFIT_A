from typing import Optional
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user_optional
from backend.app.core.rate_limit import limiter
from backend.app.models.user import User
from backend.app.services.stylist_service import StylistService
from backend.app.services.outfit_service import OutfitService
from backend.app.schemas.stylist import (
    StylistPromptRequest,
    StylistMessageOut,
    CompatibilityCheckRequest,
    CompatibilityCheckResponse
)

router = APIRouter(prefix="/stylist", tags=["AI Virtual Stylist & Styling Engine"])


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
    db: Session = Depends(get_db)
):
    service = StylistService(db)
    user_id = user.id if user else None
    return await service.interact_with_stylist(
        user_id=user_id,
        prompt=payload.prompt,
        session_id=payload.session_id,
        occasion=payload.occasion,
        budget_limit=payload.budget_limit,
        voice_input_used=payload.voice_input_used,
        recommendation_constraints=(payload.recommendation_constraints.model_dump(exclude_none=True) if payload.recommendation_constraints else None)
    )


@router.post("/compatibility", response_model=CompatibilityCheckResponse)
def check_outfit_compatibility(
    payload: CompatibilityCheckRequest,
    db: Session = Depends(get_db)
):
    service = OutfitService(db)
    return service.evaluate_compatibility(
        product_ids=payload.product_ids,
        target_occasion=payload.target_occasion or "Casual"
    )
