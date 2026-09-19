from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.exceptions import ValidationDomainError
from backend.app.models.user import AuditLog
from backend.app.services.email_service import EmailDeliveryError, is_email_configured, send_email


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
        return hashlib.sha256(("partner-lead:" + ip).encode()).hexdigest()

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
            recent_ip_count = (
                self.db.query(AuditLog)
                .filter(AuditLog.action == "partner_request_demo", AuditLog.ip_address == ip_hash, AuditLog.timestamp >= now - timedelta(hours=1))
                .count()
            )
            if recent_ip_count >= 5:
                raise ValidationDomainError("Too many partner-demo requests from this network. Please try again later.")
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
        notification_status = self._notify(row.id, details)
        details["notification_status"] = notification_status
        row.details_json = json.dumps(details, sort_keys=True)
        self.db.commit()
        return {"id": row.id, "status": details["status"], "notification_status": notification_status, "duplicate": bool(duplicate)}

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
