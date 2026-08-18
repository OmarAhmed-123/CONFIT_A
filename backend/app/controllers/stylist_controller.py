from typing import List, Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user_optional
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
async def chat_with_stylist(
    payload: StylistPromptRequest,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = StylistService(db)
    user_id = user.id if user else 1 # Guest uses default style seed context
    return await service.interact_with_stylist(
        user_id=user_id,
        prompt=payload.prompt,
        session_id=payload.session_id,
        occasion=payload.occasion,
        budget_limit=payload.budget_limit,
        voice_input_used=payload.voice_input_used
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
