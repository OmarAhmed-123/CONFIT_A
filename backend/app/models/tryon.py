from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class TryOnSession(Base):
    __tablename__ = "tryon_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=True)
    outfit_id = Column(Integer, ForeignKey("outfits.id", ondelete="SET NULL"), nullable=True)
    guest_session_token = Column(String(100), nullable=True, index=True)

    input_user_image_url = Column(String(1000), nullable=False)
    garment_image_url = Column(String(1000), nullable=True)
    rendered_result_url = Column(String(1000), nullable=True)

    applied_items_json = Column(Text, default="[]", nullable=False)
    slot_mapping_json = Column(Text, default="{}", nullable=False)
    layering_order_json = Column(Text, default="[]", nullable=False)

    status = Column(String(30), default="completed", nullable=False)  # "pending", "processing", "completed", "failed"
    body_fit_verdict = Column(String(50), default="True to Size")     # "Runs Small", "True to Size", "Relaxed Fit"
    fit_confidence_score = Column(Integer, default=94)                # AI Confidence score %
    body_scaling_factor = Column(Float, default=1.0)
    ai_disclosure_text = Column(String(255), default="AI Synthesized Garment Fit — Certified CONFIT VTON Engine v2.4")

    consent_retained = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="tryon_sessions")
    product = relationship("Product")


class VisualSearchQuery(Base):
    __tablename__ = "visual_search_queries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    input_image_url = Column(String(1000), nullable=False)
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
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

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
    body_shape = Column(String(50), default="Athletic", nullable=True)
    confidence_score = Column(Integer, default=95, nullable=False)
    calibration_method = Column(String(100), default="on_device_height_calibrated", nullable=False)
    source = Column(String(50), default="camera_estimate", nullable=False)  # "camera_estimate", "manual", "saved_profile"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    session = relationship("MeasurementSession", back_populates="results")
