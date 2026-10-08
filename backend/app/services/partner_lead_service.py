from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.exceptions import RateLimitExceededError
from backend.app.models.user import AuditLog
from backend.app.services.email_service import EmailDeliveryError, is_email_configured, send_email

logger = logging.getLogger(__name__)


class PartnerLeadService:
    """Persist public request-demo leads using the existing audit-log table.

    This avoids introducing a production-breaking schema dependency while still
    creating a durable database record and optional approved SMTP notification.
    """

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _hash_ip(ip: Optional[str]) -> Optional[str]:
        if not ip:
            return None
        return hashlib.sha256(("partner-lead:" + ip).encode()).hexdigest()[:48]

    def _recent_duplicate(self, email: str, now: datetime) -> Optional[AuditLog]:
        rows = (
            self.db.query(AuditLog)
            .filter(AuditLog.action == "partner_request_demo", AuditLog.timestamp >= now - timedelta(hours=24))
            .order_by(AuditLog.timestamp.desc())
            .limit(100)
            .all()
        )
        for row in rows:
            try:
                details = json.loads(row.details_json or "{}")
            except Exception:
                continue
            if details.get("work_email") == email:
                return row
        return None

    def submit(self, payload: Dict[str, Any], ip: Optional[str], user_agent: Optional[str]) -> Dict[str, Any]:
        email = str(payload["work_email"]).strip().lower()
        company = str(payload["company_name"]).strip()
        now = datetime.now(timezone.utc)
        duplicate = self._recent_duplicate(email, now)
        ip_hash = self._hash_ip(ip)
        if ip_hash:
            window_start = now - timedelta(hours=1)
            recent_rows = (
                self.db.query(AuditLog.timestamp)
                .filter(AuditLog.action == "partner_request_demo", AuditLog.ip_address == ip_hash, AuditLog.timestamp >= window_start)
                .order_by(AuditLog.timestamp.asc())
                .all()
            )
            if len(recent_rows) >= 5:
                # 429, not 422: this is a ceiling, not a malformed field. See
                # RateLimitExceededError — the client must be able to tell
                # "fix this input" from "stop and wait", because retrying a
                # rate limit extends the window instead of clearing it.
                #
                # Retry-After is COMPUTED, not guessed: the ceiling is a
                # sliding one-hour window, so the caller is unblocked when the
                # OLDEST of the five counted requests ages out of it. Telling
                # them a flat "try later" when we can name the real moment is
                # withholding information we already have.
                oldest = recent_rows[0][0]
                if oldest.tzinfo is None:
                    oldest = oldest.replace(tzinfo=timezone.utc)
                elapsed = (now - oldest).total_seconds()
                retry_after = max(60, int(3600 - elapsed))
                raise RateLimitExceededError(
                    "Too many partner-demo requests from this network. Please try again later.",
                    retry_after_seconds=retry_after,
                    scope="partner_lead_ip",
                )
        details = {
            "company_name": company,
            "contact_name": str(payload["contact_name"]).strip(),
            "work_email": email,
            "website": payload.get("website") or None,
            "phone": payload.get("phone") or None,
            "monthly_order_volume": payload.get("monthly_order_volume") or None,
            "message": payload.get("message") or None,
            "source_path": payload.get("source_path") or "/b2b",
            "status": "duplicate" if duplicate else "received",
            "duplicate_of_id": duplicate.id if duplicate else None,
            "user_agent": (user_agent or "")[:250] or None,
        }
        row = AuditLog(
            user_id=None,
            action="partner_request_demo",
            resource_type="partner_lead",
            resource_id=email,
            ip_address=ip_hash,
            details_json=json.dumps(details, sort_keys=True),
            after_json=json.dumps({k: details[k] for k in ("company_name", "work_email", "status", "duplicate_of_id")}, sort_keys=True),
            request_id=None,
            timestamp=now,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        # The notification outcome used to be written back INTO this row
        # (`row.details_json = ...; commit()`), i.e. an UPDATE on audit_logs.
        #
        # That is illegal on production and it 500'd every single partner-lead
        # submission: migration 0022 makes the audit tables database-restricted
        # append-only — it REVOKEs UPDATE/DELETE/TRUNCATE from the runtime role
        # AND installs a BEFORE UPDATE trigger that RAISE EXCEPTION. The INSERT
        # above succeeded, so the lead was recorded, and then the UPDATE blew up
        # and the prospect saw a 500 for a request that had actually worked.
        #
        # This was invisible to the test suite because 0022 is PostgreSQL-only
        # ("SQLite (dev): no privilege system, no plpgsql — documented no-op"),
        # so no local test could ever hit the trigger. The invariant is now
        # asserted directly in
        # test_partner_lead_submit_never_updates_audit_logs.
        #
        # The outcome is appended as its own row instead — append-only by
        # construction, and a real audit event in its own right.
        notification_status = self._notify(row.id, details)
        self._record_notification(row.id, email, notification_status, now)
        return {"id": row.id, "status": details["status"], "notification_status": notification_status, "duplicate": bool(duplicate)}

    def _record_notification(self, lead_id: int, email: str, notification_status: str,
                             now: datetime) -> None:
        """Append the notification outcome as a separate audit row.

        Best-effort by design: the lead is already durably recorded and already
        returned to the caller. A failure to persist the *outcome of the
        notification* must never turn a successful lead capture into a 500 —
        that is precisely the bug this replaces.
        """
        try:
            self.db.add(
                AuditLog(
                    user_id=None,
                    action="partner_lead_notification",
                    resource_type="partner_lead",
                    resource_id=email,
                    ip_address=None,
                    details_json=json.dumps(
                        {"lead_id": lead_id, "notification_status": notification_status},
                        sort_keys=True,
                    ),
                    after_json=json.dumps(
                        {"lead_id": lead_id, "notification_status": notification_status},
                        sort_keys=True,
                    ),
                    request_id=None,
                    timestamp=now,
                )
            )
            self.db.commit()
        except Exception:
            self.db.rollback()

    def _notify(self, lead_id: int, details: Dict[str, Any]) -> str:
        if not is_email_configured():
            return "not_configured"
        recipient = getattr(settings, "PARTNER_LEAD_NOTIFY_EMAIL", None) or getattr(settings, "EMAIL_FROM_ADDRESS", None)
        if not recipient:
            return "not_configured"
        text = (
            f"New CONFIT partner demo request\n\nCompany: {details['company_name']}\n"
            f"Contact: {details['contact_name']}\nEmail: {details['work_email']}\n"
            f"Website: {details.get('website') or '-'}\nVolume: {details.get('monthly_order_volume') or '-'}\n"
            f"Status: {details['status']}\nLead audit ID: {lead_id}\n\nMessage:\n{details.get('message') or '-'}\n"
        )
        try:
            send_email(to=recipient, subject=f"CONFIT partner demo request — {details['company_name']}", html="<pre>" + text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") + "</pre>", text=text)
            return "sent"
        except EmailDeliveryError:
            return "failed"
        except Exception as exc:
            # EmailDeliveryError is the *contracted* failure mode, but it is not
            # the only one that can escape the transport: a relay that answers
            # 200 with a non-JSON body makes json.loads raise JSONDecodeError,
            # and a malformed From header raises inside the stdlib. None of
            # those are the prospect's fault and none of them un-record the
            # lead, so none of them may surface as a 500. The lead is already
            # committed; the notification is best-effort and is recorded as
            # such by _record_notification.
            logger.warning(
                "Partner-lead notification failed with an uncontracted error "
                "(lead_id=%s): %s: %s",
                lead_id, type(exc).__name__, str(exc)[:200],
            )
            return "failed"
