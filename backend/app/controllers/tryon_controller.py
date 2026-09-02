from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.app.core.database import get_db
from backend.app.core.dependencies import get_current_user_optional
from backend.app.models.user import User
from backend.app.models.tryon import MeasurementSession, MeasurementResult
from backend.app.services.tryon_service import TryOnService
from backend.app.services.visual_search_service import VisualSearchService
from backend.app.services.no_photo_fit_service import NoPhotoFitService
from backend.app.schemas.tryon import (
    TryOnRequest,
    TryOnResponse,
    MultiGarmentTryOnRequest,
    MultiGarmentTryOnResponse,
    AnimationTryOnRequest,
    AnimationTryOnResponse,
    ImageValidationRequest,
    ImageValidationResponse,
    NoPhotoFitRequest,
    NoPhotoFitResponse,
    VisualSearchRequest,
    VisualSearchResponse,
    ApplyItemRequest,
    RemoveItemRequest,
    ReorderItemsRequest,
    MeasurementSessionCreate,
    MeasurementResultCreate,
    MeasurementSessionOut,
    TryOnJobCreate,
    TryOnJobOut,
    GarmentAssetOut
)

from backend.app.core.rate_limit import limiter

router = APIRouter(tags=["Virtual Try-On, 3D Dressing & Sizing"])


# =========================================================================
# 0. Asynchronous VTON GPU Job Queue Endpoints (Step 3 Requirement)
# =========================================================================
@router.post("/try-on/jobs", response_model=TryOnJobOut, status_code=status.HTTP_202_ACCEPTED)
@router.post("/tryon/jobs", response_model=TryOnJobOut, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("20/hour")
async def submit_tryon_job(
    request: Request,
    payload: TryOnJobCreate,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Enqueues an asynchronous Virtual Try-On inference job for GPU processing."""
    service = TryOnService(db)
    return await service.create_and_enqueue_vton_job(
        product_ids=payload.product_ids,
        user_image_url=payload.user_image_url,
        user_image_base64=payload.user_image_base64,
        avatar_model_id=payload.avatar_model_id,
        gender_mode=payload.gender_mode,
        output_aspect=payload.output_aspect,
        background_mode=payload.background_mode,
        user_id=user.id if user else None,
        consent_retain_photo=payload.consent_retain_photo
    )


@router.get("/try-on/jobs/{job_id}", response_model=TryOnJobOut)
@router.get("/tryon/jobs/{job_id}", response_model=TryOnJobOut)
def get_tryon_job_status(
    job_id: str,
    db: Session = Depends(get_db)
):
    """Polls real-time VTON inference progress, stages, and generated output image."""
    service = TryOnService(db)
    return service.get_vton_job_status(job_id)


@router.post("/try-on/jobs/{job_id}/cancel")
@router.post("/tryon/jobs/{job_id}/cancel")
def cancel_tryon_job(
    job_id: str,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = TryOnService(db)
    return service.cancel_vton_job(job_id, user_id=user.id if user else None)


@router.get("/try-on/garments/{product_id}/asset", response_model=GarmentAssetOut)
def get_garment_asset(
    product_id: int,
    db: Session = Depends(get_db)
):
    """Retrieves cached preprocessed garment masks and segmented transparent assets."""
    service = TryOnService(db)
    return service.get_or_create_garment_asset(product_id)


# =========================================================================
# 1. Multi-Garment Dynamic & Animated Try-On Endpoints
# =========================================================================
@router.post("/tryon/animation-render", response_model=AnimationTryOnResponse)
@limiter.limit("10/hour")
@router.post("/try-on/animation-render", response_model=AnimationTryOnResponse)
async def render_animated_tryon(
    request: Request,
    payload: AnimationTryOnRequest,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = TryOnService(db)
    try:
        return await service.execute_animated_tryon(
            product_ids=payload.product_ids,
            slot_mapping=payload.slot_mapping,
            user_image_url=payload.user_image_url,
            avatar_model_id=payload.avatar_model_id,
            gender_mode=payload.gender_mode,
            output_aspect=payload.output_aspect,
            background_mode=payload.background_mode,
            user_id=user.id if user else None
        )
    except RuntimeError as e:
        err = str(e)
        # Map error taxonomy to HTTP status
        if "VTON_ENGINE_UNAVAILABLE" in err:
            raise HTTPException(status_code=503, detail={"error": {"code": "VTON_ENGINE_UNAVAILABLE", "message": err}})
        elif "VTON_AUTH_FAILURE" in err:
            raise HTTPException(status_code=503, detail={"error": {"code": "VTON_AUTH_FAILURE", "message": "VTON worker authentication failed"}})
        elif "VTON_WORKER_NOT_READY" in err:
            raise HTTPException(status_code=503, detail={"error": {"code": "VTON_WORKER_NOT_READY", "message": err}})
        elif "VTON_INPUT_INVALID" in err or "VTON_GARMENT_ASSET_INVALID" in err:
            raise HTTPException(status_code=422, detail={"error": {"code": "VTON_INPUT_INVALID", "message": err}})
        elif "VTON_OUTPUT_INVALID" in err:
            raise HTTPException(status_code=502, detail={"error": {"code": "VTON_OUTPUT_INVALID", "message": err}})
        elif "VTON_TIMEOUT" in err:
            raise HTTPException(status_code=504, detail={"error": {"code": "VTON_TIMEOUT", "message": err}})
        elif "VTON_ANIMATED" in err:
            raise HTTPException(status_code=502, detail={"error": {"code": "VTON_ANIMATED_FAILED", "message": err}})
        else:
            raise HTTPException(status_code=500, detail={"error": {"code": "VTON_FAILED", "message": err[:500]}})


@router.post("/tryon/multi-render", response_model=MultiGarmentTryOnResponse)
@limiter.limit("20/hour")
@router.post("/try-on/multi-render", response_model=MultiGarmentTryOnResponse)
@router.post("/tryon/apply-garments", response_model=MultiGarmentTryOnResponse)
@router.post("/try-on/apply-garments", response_model=MultiGarmentTryOnResponse)
async def render_multi_garment_tryon(
    request: Request,
    payload: MultiGarmentTryOnRequest,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = TryOnService(db)
    try:
        return await service.execute_multi_garment_tryon(
            product_ids=payload.product_ids,
            slot_mapping=payload.slot_mapping,
            user_image_url=payload.user_image_url,
            user_image_base64=payload.user_image_base64,
            avatar_model_id=payload.avatar_model_id,
            gender_mode=payload.gender_mode,
            user_id=user.id if user else None,
            consent_retain_photo=payload.consent_retain_photo
        )
    except RuntimeError as e:
        err = str(e)
        if "VTON_ENGINE_UNAVAILABLE" in err:
            raise HTTPException(status_code=503, detail={"error": {"code": "VTON_ENGINE_UNAVAILABLE", "message": err}})
        elif "VTON_AUTH_FAILURE" in err:
            raise HTTPException(status_code=503, detail={"error": {"code": "VTON_AUTH_FAILURE", "message": "VTON worker authentication failed"}})
        elif "VTON_WORKER_NOT_READY" in err:
            raise HTTPException(status_code=503, detail={"error": {"code": "VTON_WORKER_NOT_READY", "message": err}})
        elif "VTON_INPUT_INVALID" in err:
            raise HTTPException(status_code=422, detail={"error": {"code": "VTON_INPUT_INVALID", "message": err}})
        elif "VTON_OUTPUT_INVALID" in err:
            raise HTTPException(status_code=502, detail={"error": {"code": "VTON_OUTPUT_INVALID", "message": err}})
        elif "VTON_TIMEOUT" in err:
            raise HTTPException(status_code=504, detail={"error": {"code": "VTON_TIMEOUT", "message": err}})
        else:
            raise HTTPException(status_code=500, detail={"error": {"code": "VTON_FAILED", "message": err[:500]}})


# =========================================================================
# 2. REST Session Pipeline Endpoints
# =========================================================================
class SessionInitRequest(BaseModel):
    product_id: Optional[int] = 1
    product_ids: Optional[List[int]] = []
    user_image_url: Optional[str] = None
    avatar_model_id: Optional[str] = "avatar_athletic_m"
    consent_retain: Optional[bool] = False


class ApplyMeasurementsRequest(BaseModel):
    height_cm: float
    chest_cm: Optional[float] = None
    waist_cm: Optional[float] = None
    shoulder_cm: Optional[float] = None


@router.post("/try-on/sessions/{session_id}/apply-measurements")
@router.post("/tryon/sessions/{session_id}/apply-measurements")
def apply_measurements_to_session(
    session_id: int,
    payload: ApplyMeasurementsRequest,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = TryOnService(db)
    return service.apply_measurements_to_session(
        session_id=session_id,
        height_cm=payload.height_cm,
        chest_cm=payload.chest_cm,
        waist_cm=payload.waist_cm,
        shoulder_cm=payload.shoulder_cm,
        caller_user_id=user.id if user else None,
    )


@router.post("/try-on/sessions", status_code=status.HTTP_201_CREATED)
@router.post("/tryon/sessions", status_code=status.HTTP_201_CREATED)
async def create_tryon_session(
    payload: SessionInitRequest,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = TryOnService(db)
    p_ids = payload.product_ids if payload.product_ids else ([payload.product_id] if payload.product_id else [1])
    res = await service.execute_multi_garment_tryon(
        product_ids=p_ids,
        user_image_url=payload.user_image_url,
        avatar_model_id=payload.avatar_model_id,
        user_id=user.id if user else None,
        consent_retain_photo=payload.consent_retain or False
    )
    return {
        "session_id": res["session_id"],
        "status": "ready",
        "applied_items": res["applied_items"],
        "total_price": res["total_price"],
        "rendered_result_url": res["rendered_result_url"],
        "fit_verdict": res["body_fit_verdict"],
        "expires_at": res["expires_at"]
    }


@router.get("/try-on/sessions/{session_id}")
@router.get("/tryon/sessions/{session_id}")
def get_session_details(
    session_id: int,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = TryOnService(db)
    return service.get_session_details(session_id, caller_user_id=user.id if user else None)


@router.post("/try-on/sessions/{session_id}/apply-item")
@router.post("/tryon/sessions/{session_id}/apply-item")
async def apply_item_to_session(
    session_id: int,
    payload: ApplyItemRequest,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = TryOnService(db)
    return await service.apply_item_to_session(
        session_id=session_id,
        product_id=payload.product_id,
        slot=payload.slot,
        replace_if_occupied=payload.replace_if_occupied,
        user_id=user.id if user else None
    )


@router.post("/try-on/sessions/{session_id}/remove-item")
@router.post("/tryon/sessions/{session_id}/remove-item")
async def remove_item_from_session(
    session_id: int,
    payload: RemoveItemRequest,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = TryOnService(db)
    return await service.remove_item_from_session(
        session_id=session_id,
        product_id=payload.product_id,
        slot=payload.slot,
        user_id=user.id if user else None
    )


@router.post("/try-on/sessions/{session_id}/reorder")
@router.post("/tryon/sessions/{session_id}/reorder")
def reorder_session_items(
    session_id: int,
    payload: ReorderItemsRequest,
    db: Session = Depends(get_db)
):
    service = TryOnService(db)
    return service.reorder_session_items(session_id=session_id, slot_order=payload.slot_order)


@router.delete("/try-on/sessions/{session_id}/purge")
@router.delete("/tryon/sessions/{session_id}/purge")
def purge_session(
    session_id: int,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = TryOnService(db)
    return service.purge_tryon_session(session_id, caller_user_id=user.id if user else None)


# =========================================================================
# 3. Image Validation Endpoint
# =========================================================================
@router.post("/try-on/validate-image", response_model=ImageValidationResponse)
@router.post("/tryon/validate-image", response_model=ImageValidationResponse)
def validate_user_photo(
    payload: ImageValidationRequest,
    db: Session = Depends(get_db)
):
    service = TryOnService(db)
    res = service.validate_image(payload.image_url or payload.image_base64 or "")
    return ImageValidationResponse(**res)


# =========================================================================
# 4. Single-Garment Try-On Render Endpoints
# =========================================================================
@router.post("/tryon/render", response_model=TryOnResponse)
@limiter.limit("20/hour")
@router.post("/try-on/render", response_model=TryOnResponse)
async def render_virtual_tryon(
    request: Request,
    payload: TryOnRequest,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = TryOnService(db)
    try:
        return await service.execute_tryon(
            product_id=payload.product_id,
            user_image_url=payload.user_image_url,
            user_image_base64=payload.user_image_base64,
            avatar_model_id=payload.avatar_model_id,
            user_id=user.id if user else None,
            consent_retain_photo=payload.consent_retain_photo
        )
    except RuntimeError as e:
        err = str(e)
        if "VTON_ENGINE_UNAVAILABLE" in err:
            raise HTTPException(status_code=503, detail={"error": {"code": "VTON_ENGINE_UNAVAILABLE", "message": err}})
        elif "VTON_AUTH_FAILURE" in err:
            raise HTTPException(status_code=503, detail={"error": {"code": "VTON_AUTH_FAILURE", "message": "VTON worker authentication failed"}})
        elif "VTON_WORKER_NOT_READY" in err:
            raise HTTPException(status_code=503, detail={"error": {"code": "VTON_WORKER_NOT_READY", "message": err}})
        elif "VTON_INPUT_INVALID" in err:
            raise HTTPException(status_code=422, detail={"error": {"code": "VTON_INPUT_INVALID", "message": err}})
        elif "VTON_OUTPUT_INVALID" in err:
            raise HTTPException(status_code=502, detail={"error": {"code": "VTON_OUTPUT_INVALID", "message": err}})
        elif "VTON_TIMEOUT" in err:
            raise HTTPException(status_code=504, detail={"error": {"code": "VTON_TIMEOUT", "message": err}})
        else:
            raise HTTPException(status_code=500, detail={"error": {"code": "VTON_FAILED", "message": err[:500]}})


# =========================================================================
# 5. No-Photo Fit Finder Endpoints
# =========================================================================
@router.post("/tryon/no-photo-fit", response_model=NoPhotoFitResponse)
@router.post("/try-on/no-photo-fit", response_model=NoPhotoFitResponse)
@router.post("/tryon/fit/recommend", response_model=NoPhotoFitResponse)
@router.post("/try-on/fit/recommend", response_model=NoPhotoFitResponse)
@router.post("/fit/recommend", response_model=NoPhotoFitResponse)
def compute_no_photo_fit(
    payload: NoPhotoFitRequest,
    db: Session = Depends(get_db)
):
    service = NoPhotoFitService(db)
    return service.calculate_fit(
        product_id=payload.product_id,
        height_cm=payload.height_cm,
        weight_kg=payload.weight_kg,
        body_shape=payload.body_shape,
        chest_cm=payload.chest_cm,
        waist_cm=payload.waist_cm,
        hip_cm=payload.hip_cm,
        preferred_fit=payload.preferred_fit
    )


# =========================================================================
# 6. Measurement Sessions (On-Device Client-Side Storage)
# =========================================================================
@router.post("/measurements/sessions", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
def create_measurement_session(
    payload: MeasurementSessionCreate,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    sess = MeasurementSession(
        user_id=user.id if user else None,
        status="created",
        capture_mode=payload.capture_mode,
        consent_granted=payload.consent_granted,
        save_to_profile=payload.save_to_profile
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return {
        "id": sess.id,
        "status": sess.status,
        "capture_mode": sess.capture_mode,
        "message": "Measurement session initialized. Ready for on-device landmark stream."
    }


@router.get("/measurements/sessions/{session_id}", response_model=MeasurementSessionOut)
def get_measurement_session_by_id(session_id: int, db: Session = Depends(get_db)):
    sess = db.query(MeasurementSession).filter(MeasurementSession.id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Measurement session not found")
    return sess


@router.post("/measurements/sessions/{session_id}/results", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
def submit_measurement_results(
    session_id: int,
    payload: MeasurementResultCreate,
    db: Session = Depends(get_db)
):
    sess = db.query(MeasurementSession).filter(MeasurementSession.id == session_id).first()
    if not sess:
        sess = MeasurementSession(id=session_id, status="completed", capture_mode="client_side", consent_granted=True)
        db.add(sess)
        db.flush()

    res = MeasurementResult(
        session_id=sess.id,
        height_cm=payload.height_cm,
        shoulder_width_cm=payload.shoulder_width_cm or 45.0,
        chest_cm=payload.chest_cm or 98.0,
        waist_cm=payload.waist_cm or 82.0,
        hip_cm=payload.hip_cm or 96.0,
        inseam_cm=payload.inseam_cm or 81.0,
        body_shape=payload.body_shape or "Athletic",
        body_shape_detected=payload.body_shape or "Athletic",
        confidence_score=payload.confidence_score,
        calibration_method=payload.calibration_method or "on_device_height_calibrated",
        source=payload.source or "camera_estimate"
    )
    sess.status = "completed"
    db.add(res)
    db.commit()
    db.refresh(res)

    return {
        "status": "success",
        "result_id": res.id,
        "derived_measurements": {
            "height_cm": res.height_cm,
            "shoulder_width_cm": res.shoulder_width_cm,
            "chest_cm": res.chest_cm,
            "waist_cm": res.waist_cm,
            "body_shape": res.body_shape,
            "confidence_score": res.confidence_score,
            "disclaimer": "Measurements derived from on-device pose landmarks with known stature calibration."
        }
    }


# =========================================================================
# 7. Visual Search Endpoints
# =========================================================================
@router.post("/tryon/visual-search", response_model=VisualSearchResponse)
@limiter.limit("30/hour")
@router.post("/visual-search/sessions", response_model=VisualSearchResponse)
async def visual_style_match(
    request: Request,
    payload: VisualSearchRequest,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    service = VisualSearchService(db)
    return await service.search_by_image(
        image_url=payload.image_url,
        image_base64=payload.image_base64,
        user_id=user.id if user else None,
        min_price=payload.min_price,
        max_price=payload.max_price,
        brand_ids=payload.brand_ids,
        in_stock_only=payload.in_stock_only,
        limit=payload.limit,
    )