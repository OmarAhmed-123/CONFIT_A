from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.app.core.rate_limit import limiter

from backend.app.core.database import get_db
from backend.app.schemas.stylist import PublicLookOut
from backend.app.services.outfit_service import OutfitService

router = APIRouter(prefix="/public/looks", tags=["Public Shared Looks"])


@router.get("/{token}", response_model=PublicLookOut)
@limiter.limit("60/minute")
def get_public_look(request: Request, token: str, db: Session = Depends(get_db)):
    """C8 — read-only public view of a shared look.

    Intentionally unauthenticated, but rate limited: the token is the only
    credential, so an unthrottled endpoint is an enumeration oracle. 192 bits
    of entropy make guessing infeasible anyway; the limit removes the
    incentive to try and caps scraping of shared links.

    The response DTO contains only public-safe outfit content: no user id, no
    email, no profile data, no internal ids. Unknown, revoked and EXPIRED
    tokens are all indistinguishable (404), so a probe cannot learn that a
    link once existed.
    """
    service = OutfitService(db)
    look = service.get_public_look(token)
    if not look:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shared look not found",
        )
    return look
