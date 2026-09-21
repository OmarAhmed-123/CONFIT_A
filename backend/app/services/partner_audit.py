"""Same-database atomic audit, not a best-effort post-commit delivery.

Call append_event BEFORE the business commit. Errors intentionally propagate;
Session rollback removes both business state and audit. No async outbox is
needed: audit_logs is the durable destination in this same database.
"""
import json
from uuid import uuid4
from backend.app.models.user import AuditLog
from backend.app.core.audit_redaction import scrub


def append_event(db, brand_id, action, entity, entity_id, *, before=None, after=None):
    safe_before, _ = scrub(before)
    safe_after, _ = scrub(after)
    event = AuditLog(
        brand_id=brand_id,
        user_id=db.info.get('partner_actor'),
        request_id=db.info.get('partner_request_id') or uuid4().hex,
        action=action, resource_type=entity, resource_id=str(entity_id),
        before_json=json.dumps(safe_before, default=str) if before is not None else None,
        after_json=json.dumps(safe_after, default=str) if after is not None else None,
        details_json=json.dumps({'brand_id': brand_id}),
    )
    db.add(event)
    db.flush()  # missing audit table / constraint failure must fail the mutation
    return event


def snapshot(obj, fields):
    return {field: getattr(obj, field) for field in fields}
