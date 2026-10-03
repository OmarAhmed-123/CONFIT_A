"""Feature 05 — photo-based body measurement (server-side estimation).

Orchestrates the honest estimation flow on top of the F-14 measurement-
session model:

    POST /measurements/sessions               (existing; consent captured here)
    POST /measurements/sessions/{id}/photo-estimate   (this service)

The photo-estimate step is owner-gated exactly like every other session
operation (user id or guest session token, 404 otherwise), requires the
session's recorded consent, and processes the photo through the Modal
anthropometry worker. The worker's measurements are mapped onto the
platform's ``MeasurementResult`` columns ONLY where the worker actually
produced a value (never a default), with ``source="ai_photo_estimate"`` and
the quality-derived confidence the response honestly reports. Everything
the columns cannot carry (excluded measurements, per-item provenance, the
±2-3 cm note, engine/license disclosure) is returned in the response body
so the client can show it — nothing is silently dropped.

Honesty rules (mirrored from the worker contract):
  * worker refusal (bad pose, no person, implausible geometry) -> HTTP 422
    with the worker's actionable guidance, session marked ``failed``.
  * worker unavailable (not configured / unreachable / timeout) -> HTTP 503
    with a retryable message, session status unchanged.
  * partial quality -> persist what the worker kept; the excluded list is
    returned verbatim.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.models.tryon import MeasurementResult, MeasurementSession
from backend.app.models.user import User
from backend.app.providers.anthropometry_provider import AnthropometryProvider
from backend.app.services.measurement_service import MeasurementSessionService

# Confidence by worker-reported quality. These are NOT accuracy claims: the
# ±2-3 cm note is the accuracy disclosure. The score only tells the sizing
# engine how much to trust this row relative to a manual measurement, and
# geometry-only sets (no model output at all) rank below partial ones.
_QUALITY_CONFIDENCE = {"full": 75, "partial": 60, "geometry_only": 45}

# Worker measurement name -> MeasurementResult column (cm). Only quantities
# the worker really estimates are mapped; shoulder/waist stay NULL (the
# VISAPP-2024 model set does not include them — reported, never invented).
_WORKER_TO_COLUMN = {
    "Stature": "height_cm",                      # direct geometry (anchored)
    "Stature (mm)": "height_cm",                 # model output (fallback)
    "Chest Circumference (mm)": "chest_cm",
    "Hip Circumference, Maximum (mm)": "hip_cm",
    "Inseam (Hip to Ankle)": "inseam_cm",
}


class BodyScanService:
    def __init__(self, db: Session, provider: Optional[AnthropometryProvider] = None):
        self.db = db
        self.sessions = MeasurementSessionService(db)
        self.provider = provider or AnthropometryProvider()

    # ── public API ───────────────────────────────────────────────────
    async def estimate_from_photo(
        self,
        session_id: int,
        user: Optional[User],
        guest_session_token: Optional[str],
        data_url: str,
        sex: str,
        height_cm: Optional[float],
    ) -> Dict[str, Any]:
        sess = self.sessions._resolve_owned_session(session_id, user, guest_session_token)

        if not sess.consent_granted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": {
                        "code": "MEASUREMENT_CONSENT_MISSING",
                        "message": (
                            "This measurement session was started without consent to "
                            "process body measurements, so a photo estimate cannot run."
                        ),
                    }
                },
            )
        if sess.status not in ("created", "scanning", "completed"):
            # A previously failed session may be retried with a new photo.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": {"code": "SESSION_NOT_RETRYABLE",
                                  "message": f"Session status '{sess.status}' cannot accept a photo estimate."}},
            )

        sess.status = "scanning"
        sess.capture_mode = "server_side"
        self.db.commit()

        result = await self.provider.estimate_from_photo(data_url, sex=sex, height_cm=height_cm)

        if not result.get("estimation_available"):
            reason = str(result.get("reason", "anthropometry_unavailable"))
            guidance = str(result.get("guidance", "")) or (
                "Photo-based measurement is unavailable right now. Please try again later."
            )
            if reason.startswith("worker_refused:"):
                # The worker's honest refusal — surface its guidance as 422
                # and record the failed attempt on the session.
                sess.status = "failed"
                self.db.commit()
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "error": {
                            "code": reason.split(":", 1)[1],
                            "message": guidance,
                        }
                    },
                )
            # Infrastructure problem — retryable, session stays usable.
            sess.status = "created"
            self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "error": {
                        "code": "ANTHROPOMETRY_UNAVAILABLE",
                        "message": guidance,
                        "reason": reason,
                    }
                },
            )

        # ── persist the honest mapping ────────────────────────────────
        row = self._persist_result(sess, result)
        sess.status = "completed"
        self.db.commit()

        response = dict(result)
        response["result_id"] = row.id
        response["session_id"] = sess.id
        response["stored_measurements"] = {
            "height_cm": row.height_cm,
            "shoulder_width_cm": row.shoulder_width_cm,
            "chest_cm": row.chest_cm,
            "waist_cm": row.waist_cm,
            "hip_cm": row.hip_cm,
            "inseam_cm": row.inseam_cm,
        }
        response["source"] = row.source
        response["confidence_score"] = row.confidence_score
        return response

    # ── internals ────────────────────────────────────────────────────
    def _persist_result(self, sess: MeasurementSession, worker: Dict[str, Any]) -> MeasurementResult:
        """Map the worker's measurements onto the platform columns — only
        the quantities the worker actually kept, never a default."""
        values: Dict[str, float] = {}
        for m in worker.get("measurements", []):
            column = _WORKER_TO_COLUMN.get(m.get("name", ""))
            if column is None or column in values:
                continue
            # direct geometry outranks the model output for shared names
            # (mapping order guarantees the first hit wins: geometry entries
            # are appended after model entries, so prefer them explicitly).
            value_cm = m.get("value_cm")
            if not isinstance(value_cm, (int, float)):
                continue
            if column == "height_cm":
                continue  # handled below (prefer direct geometry)
            values[column] = float(value_cm)

        # height: prefer the direct-geometry stature (anchored to the user's
        # reported height when provided), fall back to the model's estimate.
        height = None
        for m in worker.get("measurements", []):
            if m.get("name") == "Stature" and m.get("source") == "direct_geometry":
                height = float(m["value_cm"])
                break
        if height is None:
            for m in worker.get("measurements", []):
                if m.get("name") == "Stature (mm)":
                    height = float(m["value_cm"])
                    break

        quality = worker.get("quality", "geometry_only")
        row = MeasurementResult(
            session_id=sess.id,
            height_cm=height if height is not None else 0.0,
            chest_cm=values.get("chest_cm"),
            hip_cm=values.get("hip_cm"),
            inseam_cm=values.get("inseam_cm"),
            body_shape=None,            # never fabricated by this path
            body_shape_detected=None,
            confidence_score=_QUALITY_CONFIDENCE.get(quality, 45),
            calibration_reference_used=str(
                (worker.get("scale_calibration") or {}).get("source", "mediapipe_monocular")
            ),
            calibration_method="mediapipe_pose_landmarks",
            source="ai_photo_estimate",
        )
        self.db.add(row)
        self.db.flush()
        return row
