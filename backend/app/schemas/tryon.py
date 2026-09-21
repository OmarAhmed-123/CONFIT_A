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


class VtonProductCapabilityOut(BaseModel):
    product_id: int
    product_slug: Optional[str] = None
    category_slug: Optional[str] = None
    slot_type: Optional[str] = None
    state: str  # supported|unsupported|temporarily_unavailable|misconfigured|unknown
    reason_code: str
    message: str
    provider: str = "fashn_vton_segfee"


class VtonSlaOut(BaseModel):
    """Published, measurable expectations for a try-on job.

    Before this the product had no stated SLA at all, so the UI could not tell
    a user whether 40 s of waiting was normal or broken, and the backend had
    nothing to be held to. These numbers are the contract the live E2E harness
    (``backend/scripts/verify_vton_live_e2e.py``) asserts against.
    """

    warm_render_seconds_p50: float = 12.0
    warm_render_seconds_p95: float = 35.0
    # A scaled-to-zero GPU container has to boot and load the diffusion weights;
    # that is a cold start, not a failure.
    cold_start_seconds_budget: float = 120.0
    # Fail-fast window: once the circuit is open the API answers in <1 s with
    # VTON_ENGINE_UNAVAILABLE instead of burning ~39 s per request.
    fail_fast_seconds: float = 1.0
    job_timeout_seconds: float = 90.0
    delivery_ttl_seconds: float = 900.0
    max_garments_per_job: int = 8


class VtonEngineHealthOut(BaseModel):
    """Why the engine is/is not usable — from a live probe, not from env vars."""

    verdict: str  # ready|cold_start|unavailable|not_configured|unknown
    production_ready: bool
    detail: Optional[str] = None
    probe_age_seconds: Optional[float] = None
    error_code: Optional[str] = None
    circuit_state: Optional[str] = None
    retry_after_seconds: Optional[float] = None


class VtonCapabilityOut(BaseModel):
    provider: str
    # available | cold_start | temporarily_unavailable | misconfigured
    engine_state: str
    supported_slots: List[str]
    unsupported_slots: List[str]
    products: List[VtonProductCapabilityOut] = []
    # Audit closure 2026-09-21: the endpoint used to answer "available" from
    # the mere presence of VTON_WORKER_URL while the GPU workspace was disabled
    # and every job failed. The frontend now gets the real reason + the SLA.
    engine: Optional[VtonEngineHealthOut] = None
    sla: Optional[VtonSlaOut] = None
    user_message: Optional[str] = None


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
    # Honest per-layer verification outcome (all_layers_verified + failed
    # layers) so the frontend can surface a truthful quality warning when a
    # garment layer was not confirmed applied by the engine.
    verification: Optional[Dict[str, Any]] = None

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
    """Fit Finder request.

    Units are explicit (``units``) and the numeric fields are interpreted in
    THAT system: ``height`` is cm when units='metric' and inches when
    units='imperial'. Conversion happens exactly once, server-side
    (services/fit/units.py) — the previous contract assumed the client had
    already converted, so a client that converted too (or not at all) produced
    a silently wrong size.

    The legacy ``*_cm`` / ``weight_kg`` field names remain accepted for
    backward compatibility with already-deployed clients; when both are sent
    the explicit unit-neutral field wins.
    """

    product_id: int

    units: str = Field(default="metric", description="'metric' (cm/kg) or 'imperial' (in/lb)")
    height: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    weight: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    chest: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    waist: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    hip: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    shoulder: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    inseam: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    neck: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)

    # Legacy metric-named aliases (deprecated but honoured).
    height_cm: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    weight_kg: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    chest_cm: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    waist_cm: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    hip_cm: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)

    body_shape: Optional[str] = Field(
        default=None, description="Hourglass, Athletic, Rectangle, Pear, Inverted Triangle"
    )
    preferred_fit: str = "regular"
    demographic: str = Field(
        default="unisex",
        description="'men' | 'women' | 'unisex' — selects the standards chart and the estimator",
    )

    @model_validator(mode="after")
    def _validate(self):
        from backend.app.services.fit.ease import VALID_FIT_PREFERENCES

        units = (self.units or "metric").strip().lower()
        if units not in {"metric", "imperial"}:
            raise ValueError("units must be 'metric' or 'imperial'")
        object.__setattr__(self, "units", units)

        pref = (self.preferred_fit or "regular").strip().lower()
        if pref not in VALID_FIT_PREFERENCES:
            raise ValueError(
                "preferred_fit must be one of: " + ", ".join(VALID_FIT_PREFERENCES)
            )
        object.__setattr__(self, "preferred_fit", pref)

        demo = (self.demographic or "unisex").strip().lower()
        if demo not in {"men", "women", "unisex"}:
            raise ValueError("demographic must be 'men', 'women' or 'unisex'")
        object.__setattr__(self, "demographic", demo)

        # Legacy *_cm aliases are metric by definition; accepting them together
        # with units='imperial' is ambiguous, so it is rejected rather than
        # guessed.
        legacy = {
            "height_cm": self.height_cm, "weight_kg": self.weight_kg,
            "chest_cm": self.chest_cm, "waist_cm": self.waist_cm, "hip_cm": self.hip_cm,
        }
        legacy_used = [k for k, v in legacy.items() if v is not None]
        if legacy_used and units == "imperial":
            raise ValueError(
                "the legacy fields "
                + ", ".join(sorted(legacy_used))
                + " are centimetre/kilogram fields and cannot be combined with "
                "units='imperial'; send height/weight/chest/waist/hip instead"
            )

        if self.height is None and self.height_cm is None:
            raise ValueError("height is required")
        return self

    # Resolved accessors — the controller uses ONLY these, so the legacy
    # aliases never leak past the schema boundary.
    @property
    def resolved_height(self) -> float:
        return self.height if self.height is not None else self.height_cm  # type: ignore[return-value]

    @property
    def resolved_weight(self) -> Optional[float]:
        return self.weight if self.weight is not None else self.weight_kg

    @property
    def resolved_chest(self) -> Optional[float]:
        return self.chest if self.chest is not None else self.chest_cm

    @property
    def resolved_waist(self) -> Optional[float]:
        return self.waist if self.waist is not None else self.waist_cm

    @property
    def resolved_hip(self) -> Optional[float]:
        return self.hip if self.hip is not None else self.hip_cm


class NoPhotoFitResponse(BaseModel):
    """Fit Finder response.

    ``recommended`` is the field callers must branch on. When it is false the
    engine deliberately declined to name a size (missing chart, no stock, not
    enough evidence) and ``reason_code`` says which — that is a successful,
    honest response, not an error.
    """

    product_id: int
    recommended: bool
    recommended_size: Optional[str] = None
    alternative_size: Optional[str] = None
    is_between_sizes: bool = False
    # The honest headline: a rule-based band, not a probability.
    confidence_band: Optional[str] = Field(
        default=None, description="'high' | 'medium' | 'low' — deterministic, evidence-based"
    )
    confidence_band_reason: Optional[str] = None
    # Retained for backwards compatibility. Internal evidence tally in 0-100;
    # NOT a calibrated probability, so clients must not render it as "N% likely".
    confidence_score: int
    confidence_is_probability: bool = False
    confidence_factors: List[str] = Field(default_factory=list)
    is_estimated: bool = False
    fit_verdict: str
    confidence_disclosure: str
    reason_code: Optional[str] = None
    missing: List[str] = Field(default_factory=list)
    diagnostics: Dict[str, Any] = Field(default_factory=dict)
    fit_breakdown: Dict[str, str] = Field(default_factory=dict)
    size_comparison_table: List[Dict[str, Any]] = Field(default_factory=list)
    measurements_used: Dict[str, Any] = Field(default_factory=dict)
    size_chart_source: Dict[str, Any] = Field(default_factory=dict)
    garment: Dict[str, Any] = Field(default_factory=dict)
    brand_sizing_tendency: Dict[str, Any] = Field(default_factory=dict)
    return_risk: Dict[str, Any] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)
    engine_version: str
    # Legacy free-text field kept so the deployed PDP keeps rendering.
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
    score_breakdown: Optional[Dict[str, Any]] = None


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
    scoring_method: Optional[str] = None


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
    """Measurement submission.

    Bounds mirror ``services/fit/units.BOUNDS_CM`` so a value the sizing engine
    would reject can never be persisted in the first place (previously only
    height was bounded, so a 700 cm waist could be stored and then silently
    poison every later recommendation).

    ``confidence_score`` is NOT defaulted to 95 any more: a caller that does
    not know how good its measurement is must not have high confidence
    fabricated on its behalf. Omitting it stores NULL-equivalent low confidence
    for the manual path (50) and requires the client to state its own value.
    """

    units: str = Field(default="metric", description="'metric' (cm) or 'imperial' (in)")
    height_cm: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    height: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    shoulder_width_cm: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    chest_cm: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    waist_cm: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    hip_cm: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    inseam_cm: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    body_shape: Optional[str] = None
    confidence_score: int = Field(default=50, ge=1, le=100)
    calibration_method: str = "manual_entry"
    source: str = "manual"

    @model_validator(mode="after")
    def _validate(self):
        units = (self.units or "metric").strip().lower()
        if units not in {"metric", "imperial"}:
            raise ValueError("units must be 'metric' or 'imperial'")
        object.__setattr__(self, "units", units)
        if self.height is None and self.height_cm is None:
            raise ValueError("height is required")
        if units == "imperial" and self.height_cm is not None:
            raise ValueError(
                "height_cm is a centimetre field and cannot be combined with units='imperial'; "
                "send 'height' instead"
            )
        return self

    def to_canonical(self) -> "MeasurementResultCreate":
        """Convert to centimetres and bounds-check, once, at the boundary."""
        from backend.app.services.fit.units import BodyMeasurements, UnitSystem

        body = BodyMeasurements.from_payload(
            units=UnitSystem(self.units),
            height=self.height if self.height is not None else self.height_cm,
            chest=self.chest_cm if self.units == "metric" else None,
            waist=self.waist_cm if self.units == "metric" else None,
            hip=self.hip_cm if self.units == "metric" else None,
            shoulder=self.shoulder_width_cm if self.units == "metric" else None,
            inseam=self.inseam_cm if self.units == "metric" else None,
            body_shape=self.body_shape,
        ) if self.units == "metric" else BodyMeasurements.from_payload(
            units=UnitSystem.IMPERIAL,
            height=self.height,
            chest=self.chest_cm,
            waist=self.waist_cm,
            hip=self.hip_cm,
            shoulder=self.shoulder_width_cm,
            inseam=self.inseam_cm,
            body_shape=self.body_shape,
        )
        return MeasurementResultCreate(
            units="metric",
            height_cm=body.height_cm,
            shoulder_width_cm=body.shoulder_cm,
            chest_cm=body.chest_cm,
            waist_cm=body.waist_cm,
            hip_cm=body.hip_cm,
            inseam_cm=body.inseam_cm,
            body_shape=self.body_shape,
            confidence_score=self.confidence_score,
            calibration_method=self.calibration_method,
            source=self.source,
        )


class MeasurementResultOut(BaseModel):
    id: int
    session_id: int
    height_cm: float
    shoulder_width_cm: Optional[float]
    chest_cm: Optional[float]
    waist_cm: Optional[float]
    hip_cm: Optional[float]
    inseam_cm: Optional[float]
    # Nullable on purpose: "not stated" is a real state and must not be
    # rendered as a fabricated default body shape.
    body_shape: Optional[str] = None
    confidence_score: int
    calibration_method: Optional[str] = None
    source: Optional[str] = None
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
