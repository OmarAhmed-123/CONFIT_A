"""Measurement-session authorization service (F-14 fix).

Security context
----------------
The measurement-session routes (``/measurements/sessions``) were reachable
with **no authentication and no ownership check**: any anonymous request
could read any session by enumerating the sequential integer id (exposing
``user_id`` and the stored body measurements) and could POST results to an
unknown id, which **auto-created a session with ``consent_granted=True``**
— a consent-fabrication and PII-write vector.

Authorization model (established app patterns, no new identity system)
----------------------------------------------------------------------
* Authenticated flow: the session is bound to the server-resolved
  ``user.id`` at creation. Every later operation requires that the
  server-side authenticated user is the session owner.
* Guest flow: the app-wide guest pattern is the ``X-Session-Token`` header
  (the same header ``apiClient.ts`` attaches to every request and that
  ``/tryon/visual-search`` already uses for guest scoping). A guest session
  is bound to that token at creation and every later operation requires
  the same token.
* Unknown or foreign sessions always yield **404** — the same response for
  "does not exist" and "not yours" (no ownership oracle).
* Consent is captured **only** at session creation (the explicit camera-scan
  start action in the UI) and persisted server-side on the session row.
  Result submission can never set, change, or fabricate consent, and a
  missing session can never be auto-created by a results POST.
"""

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.models.tryon import MeasurementResult, MeasurementSession
from backend.app.schemas.tryon import MeasurementResultCreate
from backend.app.models.user import User


def _not_found() -> HTTPException:
    # Single error shape for both "unknown" and "not owner" — no oracle.
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Measurement session not found",
    )


class MeasurementSessionService:
    def __init__(self, db: Session):
        self.db = db

    # ── ownership resolution ──────────────────────────────────────────────
    def _resolve_owned_session(
        self,
        session_id: int,
        user: Optional[User],
        guest_session_token: Optional[str],
    ) -> MeasurementSession:
        """Return the session only if the caller demonstrably owns it.

        Owner = the authenticated user the session was created for, or the
        holder of the guest session token the session was bound to.
        Anything else — including "no identity at all" — is 404.
        """
        sess = (
            self.db.query(MeasurementSession)
            .filter(MeasurementSession.id == session_id)
            .first()
        )
        if sess is None:
            raise _not_found()

        if user is not None and sess.user_id is not None and sess.user_id == user.id:
            return sess

        if (
            guest_session_token
            and sess.user_id is None
            and sess.guest_session_token
            and sess.guest_session_token == guest_session_token
        ):
            return sess

        raise _not_found()

    # ── creation ──────────────────────────────────────────────────────────
    def create_session(
        self,
        user: Optional[User],
        guest_session_token: Optional[str],
        capture_mode: str,
        consent_granted: bool,
        save_to_profile: bool,
    ) -> MeasurementSession:
        """Create a session bound to exactly one identity.

        * Authenticated caller  -> bound to ``user.id`` (server-resolved).
        * Guest caller          -> bound to the provided ``X-Session-Token``
          (the app's established guest-session header). A guest request with
          no token is rejected: an unbindable session is exactly the shape
          of the F-14 hole.
        """
        if user is None and not guest_session_token:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="A session token or authenticated identity is required to start a measurement session.",
            )

        sess = MeasurementSession(
            user_id=user.id if user is not None else None,
            guest_session_token=None if user is not None else guest_session_token,
            status="created",
            capture_mode=capture_mode,
            # Consent is the caller's explicit declaration at session start
            # (the camera-scan modal action) and is persisted as-is. The
            # column default is False: nothing is ever *assumed* granted.
            consent_granted=bool(consent_granted),
            save_to_profile=bool(save_to_profile) if user is not None else False,
        )
        self.db.add(sess)
        self.db.commit()
        self.db.refresh(sess)
        return sess

    # ── read ──────────────────────────────────────────────────────────────
    def get_session(
        self,
        session_id: int,
        user: Optional[User],
        guest_session_token: Optional[str],
    ) -> MeasurementSession:
        return self._resolve_owned_session(session_id, user, guest_session_token)

    # ── results ───────────────────────────────────────────────────────────
    def submit_results(
        self,
        session_id: int,
        user: Optional[User],
        guest_session_token: Optional[str],
        payload: MeasurementResultCreate,
    ) -> MeasurementResult:
        """Append a measurement result to an EXISTING, caller-owned session.

        No auto-creation (an unknown id is 404), no consent mutation, and no
        fabricated default body dimensions — omitted measurements are stored
        as NULL, exactly as reported.
        """
        sess = self._resolve_owned_session(session_id, user, guest_session_token)

        res = MeasurementResult(
            session_id=sess.id,
            height_cm=payload.height_cm,
            shoulder_width_cm=payload.shoulder_width_cm,
            chest_cm=payload.chest_cm,
            waist_cm=payload.waist_cm,
            hip_cm=payload.hip_cm,
            inseam_cm=payload.inseam_cm,
            body_shape=payload.body_shape,
            body_shape_detected=payload.body_shape,
            confidence_score=payload.confidence_score,
            calibration_method=payload.calibration_method,
            source=payload.source,
        )
        sess.status = "completed"
        self.db.add(res)
        self.db.commit()
        self.db.refresh(res)
        return res
