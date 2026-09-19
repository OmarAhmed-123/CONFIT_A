from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.exceptions import ValidationDomainError
from backend.app.models.user import PartnerLead
from backend.app.services.email_service import EmailDeliveryError, is_email_configured, send_email


class PartnerLeadService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _hash_ip(ip: Optional[str]) -> Optional[str]:
        if not ip:
            return None
        return hashlib.sha256(("partner-lead:" + ip).encode()).hexdigest()

    def submit(self, payload: Dict[str, Any], ip: Optional[str], user_agent: Optional[str]) -> PartnerLead:
        email = str(payload["work_email"]).strip().lower()
        company = str(payload["company_name"]).strip()
        now = datetime.now(timezone.utc)
        recent_same_email = (
            self.db.query(PartnerLead)
            .filter(PartnerLead.work_email == email, PartnerLead.created_at >= now - timedelta(hours=24))
            .order_by(PartnerLead.created_at.desc())
            .first()
        )
        ip_hash = self._hash_ip(ip)
        if ip_hash:
            recent_ip_count = (
                self.db.query(PartnerLead)
                .filter(PartnerLead.ip_hash == ip_hash, PartnerLead.created_at >= now - timedelta(hours=1))
                .count()
            )
            if recent_ip_count >= 5:
                raise ValidationDomainError("Too many partner-demo requests from this network. Please try again later.")
        lead = PartnerLead(
            company_name=company,
            contact_name=str(payload["contact_name"]).strip(),
            work_email=email,
            website=(payload.get("website") or None),
            phone=(payload.get("phone") or None),
            monthly_order_volume=(payload.get("monthly_order_volume") or None),
            message=(payload.get("message") or None),
            status="duplicate" if recent_same_email else "received",
            notification_status="not_configured",
            duplicate_of_id=recent_same_email.id if recent_same_email else None,
            source_path=payload.get("source_path") or "/b2b",
            ip_hash=ip_hash,
            user_agent=(user_agent or "")[:500] or None,
        )
        self.db.add(lead)
        self.db.commit()
        self.db.refresh(lead)
        self._notify(lead)
        self.db.commit()
        self.db.refresh(lead)
        return lead

    def _notify(self, lead: PartnerLead) -> None:
        if not is_email_configured():
            lead.notification_status = "not_configured"
            return
        recipient = getattr(settings, "PARTNER_LEAD_NOTIFY_EMAIL", None) or getattr(settings, "EMAIL_FROM_ADDRESS", None)
        if not recipient:
            lead.notification_status = "not_configured"
            return
        safe_text = (
            f"New CONFIT partner demo request\n\n"
            f"Company: {lead.company_name}\nContact: {lead.contact_name}\nEmail: {lead.work_email}\n"
            f"Website: {lead.website or '-'}\nVolume: {lead.monthly_order_volume or '-'}\n"
            f"Status: {lead.status}\nLead ID: {lead.id}\n\nMessage:\n{lead.message or '-'}\n"
        )
        try:
            send_email(
                to=recipient,
                subject=f"CONFIT partner demo request — {lead.company_name}",
                html="<pre>" + safe_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") + "</pre>",
                text=safe_text,
            )
            lead.notification_status = "sent"
        except EmailDeliveryError:
            lead.notification_status = "failed"
