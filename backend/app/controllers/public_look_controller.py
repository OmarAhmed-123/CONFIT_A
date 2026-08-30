from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.schemas.stylist import PublicLookOut
from backend.app.services.outfit_service import OutfitService

router = APIRouter(prefix="/public/looks", tags=["Public Shared Looks"])


@router.get("/{token}", response_model=PublicLookOut)
def get_public_look(token: str, db: Session = Depends(get_db)):
    """C8 — read-only public view of a shared look.

    Intentionally unauthenticated. The response DTO contains only public-safe
    outfit content: no user id, no email, no profile data, no internal ids.
    Unknown / revoked tokens are indistinguishable (404).
    """
    service = OutfitService(db)
    look = service.get_public_look(token)
    if not look:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shared look not found",
        )
    return look
