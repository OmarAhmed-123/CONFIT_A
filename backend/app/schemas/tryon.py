from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, model_validator


class TryOnJobCreate(BaseModel):
    product_ids: List[int]
    user_image_url: Optional[str] = None
    user_image_base64: Optional[str] = None
    avatar_model_id: Optional[str] = "avatar_athletic_m"
    gender_mode: Optional[str] = "infer_from_image"
    output_aspect: Optional[str] = "9:16"
    background_mode: Optional[str] = "studio"
    consent_retain_photo: bool = False


class TryOnJobDeliveryOut(BaseModel):
    """Temporary-delivery reference — returned ONLY in the authenticated
    completion response (never on polling, never to non-owners).

    The generated image is not stored durably (product requirement): the
    guaranteed vehicle is ``result_image_data_url`` on the same response;
    ``download_url`` + ``token`` back a one-shot, TTL-bounded, process-local
    download (best effort on serverless — 410 GONE when the instance no
    longer holds the staged copy).
    """
    download_url: str
    token: str
    expires_at: Optional[datetime] = None
    content_type: Optional[str] = None
    byte_size: Optional[int] = None
    ttl_seconds: Optional[float] = None
    one_time: bool = True
    # Contract (2026-09-05, hardening): the GUARANTEED delivery carrier —
    # and the only download path the product promises — is
    # `result_image_data_url` on the same authenticated response; the
    # frontend renders it and offers the user download as a client-side
    # Blob (no server round-trip, works on every instance). `download_url`
    # is an opportunistic one-shot cache that is NOT a product download
    # promise: it can return 410 GONE within the TTL when Vercel routes the
    # GET to an instance that did not stage the bytes. `ttl_seconds`
    # describes the cache, not a download availability guarantee.
    carrier: str = "in_response"
    guaranteed_field: str = "result_image_data_url"
    download_note: Optional[str] = None


class TryOnJobOut(BaseModel):
    id: int
    job_id: str
    status: str
    progress_pct: int
    current_stage: str
    model_used: str
    # Never a stored image reference: the VTON flow leaves it NULL (generated
    # images are delivered temporarily and not persisted).
    output_image_url: Optional[str] = None
    # Guaranteed in-response delivery of the generated image (completion
    # response only; absent on polling and failure payloads).
    result_image_data_url: Optional[str] = None
    delivery: Optional[TryOnJobDeliveryOut] = None
    delivery_expires_at: Optional[datetime] = None
    metrics: Dict[str, Any] = {}
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class GarmentAssetOut(BaseModel):
    id: int
    product_id: int
    slot_type: str
    flat_image_url: str
    segmented_garment_url: Optional[str] = None
    garment_mask_url: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApplyItemRequest(BaseModel):
    product_id: int
    slot: Optional[str] = None
    replace_if_occupied: bool = True


class RemoveItemRequest(BaseModel):
    product_id: Optional[int] = None
    slot: Optional[str] = None


class ReorderItemsRequest(BaseModel):
    slot_order: List[str]


class TryOnRequest(BaseModel):
    product_id: int
    user_image_url: Optional[str] = None
    user_image_base64: Optional[str] = None
    avatar_model_id: Optional[str] = "avatar_athletic_m"
    consent_retain_photo: bool = False
    custom_adjustments: Optional[Dict[str, Any]] = None


class TryOnResponse(BaseModel):
    session_id: int
    product_id: int
    product_title: str
    brand_name: str
    status: str
    original_item_image: str
    rendered_result_url: str
    fit_confidence_score: int
    body_fit_verdict: str
    recommended_size: str
    ai_disclosure: str
    traceability_hash: str
    expires_at: Optional[datetime] = None


class AppliedGarmentOut(BaseModel):
    product_id: int
    product_title: str
    brand_name: str
    category_name: str
    position: str  # "upper_outer", "upper_inner", "lower", "dress", "footwear", "accessory"
    image_url: str
    color_family: Optional[str] = None
    color_hex: Optional[str] = "#1B1F3B"
    material: Optional[str] = None
    price: float
    selected_size: Optional[str] = "M"
    layer_order: int = 1

    model_config = ConfigDict(from_attributes=True)


class MultiGarmentTryOnRequest(BaseModel):
    product_ids: Optional[List[int]] = []
    slot_mapping: Optional[Dict[str, int]] = {}
    user_image_url: Optional[str] = None
    user_image_base64: Optional[str] = None
    avatar_model_id: Optional[str] = "avatar_athletic_m"
    gender_mode: Optional[str] = "infer_from_image"
    pose_mode: Optional[str] = "standing_front"
    background_mode: Optional[str] = "luxury_studio"
    body_preservation_mode: str = "strict"
    face_preservation_mode: str = "strict"
    consent_retain_photo: bool = False


class MultiGarmentTryOnResponse(BaseModel):
    session_id: int
    status: str
    user_reference_image: str
    rendered_result_url: str
    before_after_split_url: Optional[str] = None
    applied_items: List[AppliedGarmentOut] = []
    total_price: float
    fit_confidence_score: int
    body_fit_verdict: str
    recommended_sizes: Dict[str, str] = {}
    ai_disclosure: str
    traceability_hash: str
    layering_order: List[str] = []
    dynamic_prompt_generated: Optional[str] = None
    expires_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AnimationKeyframeOut(BaseModel):
    step: int
    slot: str
    product_title: str
    brand_name: str
    image_url: str
    status: str

    model_config = ConfigDict(from_attributes=True)


class AnimationTryOnRequest(BaseModel):
    product_ids: Optional[List[int]] = []
    slot_mapping: Optional[Dict[str, int]] = {}
    user_image_url: Optional[str] = None
    avatar_model_id: Optional[str] = "avatar_athletic_m"
    gender_mode: Optional[str] = "infer_from_image"
    output_aspect: Optional[str] = "9:16"
    background_mode: Optional[str] = "studio"
    animation_style: Optional[str] = "premium_realistic"


class AnimationTryOnResponse(BaseModel):
    session_id: int
    status: str
    animation_style: str
    output_aspect: str
    rendered_animation_url: str
    keyframes_sequence: List[AnimationKeyframeOut] = []
    fit_confidence_score: int
    body_fit_verdict: str
    traceability_hash: str
    ai_disclosure: str
    dynamic_animation_prompt: str
    applied_items: List[AppliedGarmentOut] = []
    total_price: float

    model_config = ConfigDict(from_attributes=True)


class ImageValidationRequest(BaseModel):
    image_url: Optional[str] = None
    image_base64: Optional[str] = None


class ImageValidationResponse(BaseModel):
    is_valid: bool
    format: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    aspect_ratio: Optional[float] = None
    min_dimension: Optional[int] = None
    size_bytes: Optional[int] = None
    issues: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    # Vision-derived fields stay honest nulls unless a real model analysis ran.
    detected_category: Optional[str] = None
    detected_gender: Optional[str] = None
    body_framing: Optional[str] = None
    resolution_status: Optional[str] = None
    lighting_quality: Optional[str] = None


class NoPhotoFitRequest(BaseModel):
    product_id: int
    height_cm: float = Field(ge=100, le=250)
    weight_kg: float = Field(ge=30, le=250)
    body_shape: str = Field(description="Hourglass, Athletic, Rectangle, Pear, Inverted Triangle")
    chest_cm: Optional[float] = None
    waist_cm: Optional[float] = None
    hip_cm: Optional[float] = None
    preferred_fit: str = "regular"


class NoPhotoFitResponse(BaseModel):
    product_id: int
    recommended_size: str
    confidence_score: int
    fit_breakdown: Dict[str, str]
    size_comparison_table: List[Dict[str, Any]]
    brand_sizing_tendency: str
    return_risk_score: str


class VisualSearchRequest(BaseModel):
    image_url: Optional[str] = None
    image_base64: Optional[str] = None
    top_k: int = Field(default=8, ge=1, le=20)
    min_price: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    max_price: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    brand_ids: Optional[List[int]] = None
    in_stock_only: bool = False

    @model_validator(mode="after")
    def _validate_price_range(self):
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError("min_price must not exceed max_price")
        return self


class VisualSearchResultItem(BaseModel):
    product_id: int
    title: str
    brand_name: str
    price: float
    image_url: str
    similarity_score: int
    detected_color: str
    match_type: str


class VisualSearchResponse(BaseModel):
    query_id: int
    analysis_available: bool = False
    analysis_source: Optional[str] = None
    detected_category: Optional[str] = None
    detected_color: Optional[str] = None
    detected_pattern: Optional[str] = None
    detected_style: Optional[str] = None
    results_count: int
    matches: List[VisualSearchResultItem]


# Measurement Flow Schemas
class MeasurementSessionCreate(BaseModel):
    capture_mode: str = Field(default="client_side", description="'client_side', 'server_side', 'manual'")
    # F-14: consent is the caller's explicit declaration at session start and
    # is persisted as-is. Default is False — missing consent is NEVER
    # assumed granted. Only the intended product flow (the camera-scan
    # start action) sends true.
    consent_granted: bool = False
    save_to_profile: bool = False


class MeasurementResultCreate(BaseModel):
    height_cm: float = Field(ge=100, le=250)
    shoulder_width_cm: Optional[float] = None
    chest_cm: Optional[float] = None
    waist_cm: Optional[float] = None
    hip_cm: Optional[float] = None
    inseam_cm: Optional[float] = None
    body_shape: Optional[str] = "Athletic"
    confidence_score: int = Field(default=95, ge=50, le=100)
    calibration_method: str = "on_device_height_calibrated"
    source: str = "camera_estimate"


class MeasurementResultOut(BaseModel):
    id: int
    session_id: int
    height_cm: float
    shoulder_width_cm: Optional[float]
    chest_cm: Optional[float]
    waist_cm: Optional[float]
    hip_cm: Optional[float]
    inseam_cm: Optional[float]
    body_shape: str
    confidence_score: int
    calibration_method: str
    source: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MeasurementSessionOut(BaseModel):
    id: int
    # F-14: user_id is intentionally not exposed — leaking the owner id of a
    # session (even to its owner's own token holder is unnecessary) enables
    # user enumeration. Ownership is proven by access, not by disclosure.
    status: str
    capture_mode: str
    consent_granted: bool
    save_to_profile: bool
    results: List[MeasurementResultOut] = []
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
