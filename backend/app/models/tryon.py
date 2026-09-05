import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float, TypeDecorator
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class TryOnJobStatus(str, enum.Enum):
    QUEUED = "queued"
    PARSING_PERSON = "parsing_person"
    WARPING_GARMENT = "warping_garment"
    DIFFUSION_RENDERING = "diffusion_rendering"
    HARMONIZING = "harmonizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TryOnJobStatusType(TypeDecorator):
    """Stores the job status as a plain string (the enum VALUE, e.g. 'queued') —
    consistent with UserRoleType and with the production schema, which must be
    VARCHAR. Native Postgres ENUM columns caused 42804 insert failures after a
    model revision changed (the 2026-08-29 signup/jobs 500)."""
    impl = String(30)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, TryOnJobStatus):
            return value.value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return TryOnJobStatus(value)
        except ValueError:
            return value


class TryOnJob(Base):
    """Asynchronous Virtual Try-On GPU Inference Job."""
    __tablename__ = "tryon_jobs"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String(64), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    session_id = Column(Integer, ForeignKey("tryon_sessions.id", ondelete="SET NULL"), nullable=True)
    status = Column(
        TryOnJobStatusType(),
        default=TryOnJobStatus.QUEUED,
        nullable=False
    )
    progress_pct = Column(Integer, default=0, nullable=False)
    current_stage = Column(String(50), default="queued", nullable=False)
    input_person_image_url = Column(Text, nullable=False)
    garment_ids_json = Column(Text, default="[]", nullable=False)
    garment_layers_json = Column(Text, default="[]", nullable=False)
    model_used = Column(String(50), default="unset", nullable=False)
    # NEVER a stored image reference: generated try-on images are delivered
    # temporarily (in the authenticated response + one-shot TTL download) and
    # must not be persisted (product requirement, 2026-09-05). Kept nullable
    # for schema compatibility; the VTON flow leaves it NULL.
    output_image_url = Column(Text, nullable=True)
    # Temporary-delivery metadata ONLY (no image bytes, no object keys, no
    # public URLs): the SHA-256 hash of the one-time delivery token (the
    # plaintext token exists only in the completion response and the caller's
    # memory) plus the expiry of the process-local staged copy.
    delivery_token_hash = Column(String(64), nullable=True, index=True)
    delivery_expires_at = Column(DateTime, nullable=True)
    delivery_content_type = Column(String(50), nullable=True)
    metrics_json = Column(Text, default="{}", nullable=False)  # SSIM, LPIPS, execution time
    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    user = relationship("User")
    session = relationship("TryOnSession")


class GarmentAsset(Base):
    """Preprocessed Garment Assets with cached masks and transparent cutouts."""
    __tablename__ = "garment_assets"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    slot_type = Column(String(50), nullable=False)  # upper_outer, upper_inner, lower, dress, footwear, accessory
    flat_image_url = Column(Text, nullable=False)
    segmented_garment_url = Column(Text, nullable=True)
    garment_mask_url = Column(Text, nullable=True)
    bounding_box_json = Column(Text, default="{}", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    product = relationship("Product")


class PersonScanCache(Base):
    """Cached Human Parsing and Pose Keypoints per Image Hash."""
    __tablename__ = "person_scan_cache"

    id = Column(Integer, primary_key=True, index=True)
    image_hash = Column(String(64), unique=True, index=True, nullable=False)
    segmentation_mask_url = Column(Text, nullable=True)
    pose_keypoints_json = Column(Text, default="{}", nullable=False)
    body_shape_detected = Column(String(50), default="Athletic", nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class TryOnSession(Base):
    __tablename__ = "tryon_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    guest_session_token = Column(String(100), nullable=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=True)
    outfit_id = Column(Integer, ForeignKey("outfits.id", ondelete="SET NULL"), nullable=True)
    user_image_url = Column(Text, nullable=True)
    input_user_image_url = Column(Text, nullable=True)
    garment_image_url = Column(Text, nullable=True)
    rendered_image_url = Column(Text, nullable=True)
    rendered_result_url = Column(Text, nullable=True)
    rendered_animation_url = Column(Text, nullable=True)
    status = Column(String(30), default="completed", nullable=False)  # "pending", "processing", "completed", "failed"
    fit_verdict = Column(String(50), default="True to Size", nullable=False)
    fit_confidence_score = Column(Integer, default=95, nullable=False)
    body_fit_verdict = Column(String(100), default="True to Size (Optimal Drape)", nullable=True)
    body_scaling_factor = Column(Float, default=1.0, nullable=False)
    ai_disclosure_text = Column(String(500), default="AI Synthesized Garment Drape", nullable=True)
    ai_disclosure = Column(String(500), default="AI Synthesized Garment Drape", nullable=True)
    applied_items_json = Column(Text, default="[]", nullable=False)  # Multi-garment layers
    slot_mapping_json = Column(Text, default="{}", nullable=True)
    layering_order_json = Column(Text, default="[]", nullable=True)
    render_metadata_json = Column(Text, default="{}", nullable=False)
    traceability_hash = Column(String(100), nullable=True)
    consent_retained = Column(Boolean, default=False, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="tryon_sessions")
    product = relationship("Product")


class VisualSearchQuery(Base):
    __tablename__ = "visual_search_queries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    input_image_url = Column(Text, nullable=False)
    detected_category = Column(String(100), nullable=True)
    detected_color = Column(String(50), nullable=True)
    detected_pattern = Column(String(50), nullable=True)
    detected_style = Column(String(100), nullable=True)
    detected_attributes_json = Column(Text, default="{}", nullable=False)
    matches_json = Column(Text, default="[]", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class MeasurementSession(Base):
    __tablename__ = "measurement_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    guest_session_token = Column(String(100), nullable=True, index=True)
    status = Column(String(30), default="created", nullable=False)  # "created", "scanning", "completed", "failed"
    capture_mode = Column(String(30), default="client_side", nullable=False)  # "client_side", "server_side", "manual"
    consent_granted = Column(Boolean, default=True, nullable=False)
    save_to_profile = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User")
    results = relationship("MeasurementResult", back_populates="session", cascade="all, delete-orphan")


class MeasurementResult(Base):
    __tablename__ = "measurement_results"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("measurement_sessions.id", ondelete="CASCADE"), nullable=False)
    height_cm = Column(Float, nullable=False)
    shoulder_width_cm = Column(Float, nullable=True)
    chest_cm = Column(Float, nullable=True)
    waist_cm = Column(Float, nullable=True)
    hip_cm = Column(Float, nullable=True)
    inseam_cm = Column(Float, nullable=True)
    body_shape_detected = Column(String(50), nullable=True)
    body_shape = Column(String(50), nullable=True)
    confidence_score = Column(Integer, default=95, nullable=False)
    calibration_reference_used = Column(String(100), default="device_accelerometer_ruler", nullable=False)
    calibration_method = Column(String(100), default="device_ruler", nullable=True)
    source = Column(String(50), default="camera_vision", nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    session = relationship("MeasurementSession", back_populates="results")
