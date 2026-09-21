"""Audit-trail policy layer (G-05, G-06).

Sits between the controller and ``AuditRepository`` and owns the decisions that
are *policy* rather than *data*: pagination caps, actor enrichment, the
before/after diff, the integrity self-check and its honest limitations.

Layering follows the rest of the backend (controller → service → repository →
SQLAlchemy) so the same policy is applied no matter which endpoint asks.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.app.models.user import AuditLog
from backend.app.repositories.audit_repository import AuditQuery, AuditRepository

MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50
MAX_WINDOW_DAYS = 365


def _loads(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        # An unparsable payload is surfaced as-is rather than silently dropped:
        # losing audit detail quietly is worse than showing an odd string.
        return {"_unparsable": raw[:500]}
    return parsed if isinstance(parsed, dict) else {"_value": parsed}


def diff_fields(before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]]) -> List[str]:
    """Names of the fields the action actually changed — the question an
    auditor asks first, previously only answerable by diffing JSON by eye."""
    if before is None and after is None:
        return []
    before = before or {}
    after = after or {}
    changed = [key for key in set(before) | set(after) if before.get(key) != after.get(key)]
    return sorted(changed)


def _actor_label(user_id: Optional[int], identities: Dict[int, Dict[str, Any]]) -> Tuple[str, Optional[str], Optional[str]]:
    if user_id is None:
        return "system", None, None
    ident = identities.get(int(user_id))
    if not ident:
        # Actor row is gone (deleted account). Say so instead of inventing an
        # identity — an unresolvable actor is itself a governance finding.
        return f"user:{user_id} (unresolved)", None, None
    return ident.get("email") or f"user:{user_id}", ident.get("email"), ident.get("role")


class AuditTrailService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = AuditRepository(db)

    # --- normalisation --------------------------------------------------
    @staticmethod
    def clamp_page(page: int, page_size: int) -> Tuple[int, int]:
        page = max(1, int(page or 1))
        page_size = min(MAX_PAGE_SIZE, max(1, int(page_size or DEFAULT_PAGE_SIZE)))
        return page, page_size

    # --- trail ----------------------------------------------------------
    def trail(
        self,
        query: AuditQuery,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        include_facets: bool = False,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        page, page_size = self.clamp_page(page, page_size)
        rows, total = self.repo.page(query, page, page_size)
        identities = self.repo.actor_identities([row.user_id for row in rows])

        items = [self._serialise(row, identities) for row in rows]
        total_pages = max(1, (total + page_size - 1) // page_size)
        payload: Dict[str, Any] = {
            "items": items,
            "meta": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_previous": page > 1,
            },
            "filters": query.as_public_dict(),
            "request_id": request_id,
        }
        if include_facets:
            facets = self.repo.facets(query)
            facets["actors"] = self.repo.actors(query)
            payload["facets"] = facets
        return payload

    def _serialise(self, row: AuditLog, identities: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
        actor, email, role = _actor_label(row.user_id, identities)
        before = _loads(row.before_json)
        after = _loads(row.after_json)
        return {
            "id": row.id,
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "actor": actor,
            "actor_id": row.user_id,
            "actor_email": email,
            "actor_role": role,
            "ip_address": row.ip_address,
            "request_id": row.request_id,
            "details": row.details_json,
            "before": before,
            "after": after,
            "changed_fields": diff_fields(before, after),
            "timestamp": row.timestamp,
        }

    # --- facets / stats -------------------------------------------------
    def facets(self, query: AuditQuery) -> Dict[str, Any]:
        out = self.repo.facets(query)
        out["actors"] = self.repo.actors(query)
        return out

    def stats(self, query: AuditQuery, window_days: int = 30) -> Dict[str, Any]:
        window_days = min(MAX_WINDOW_DAYS, max(1, int(window_days or 30)))
        scoped = AuditQuery(
            action=query.action,
            resource_type=query.resource_type,
            actor_id=query.actor_id,
            date_from=query.date_from,
            date_to=query.date_to,
            only_admin_actions=query.only_admin_actions,
        )
        facet = self.repo.facets(scoped, limit=50)
        _, _, _, _, distinct_actors = self.repo.bounds(window_days)
        return {
            "window_days": window_days,
            "total_events": self.repo.count(scoped),
            "by_action": facet["actions"],
            "by_resource_type": facet["resource_types"],
            "by_actor": self.repo.actors(scoped, limit=50),
            "by_day": self.repo.by_day(scoped),
            "distinct_actors": int(distinct_actors),
            "admin_action_events": self.repo.admin_action_count(window_days),
        }

    # --- integrity ------------------------------------------------------
    def integrity(self, window_days: int = 30, sample_limit: int = 500) -> Dict[str, Any]:
        """Structural self-check over real rows, with its limits stated.

        Returns concrete violations rather than a boolean, because "the audit
        log is fine" is exactly the kind of unverifiable claim this feature is
        supposed to eliminate.
        """
        from datetime import datetime, timedelta, timezone

        from backend.app.core.audit_redaction import REDACTED_PREFIX, contains_secret

        window_days = min(MAX_WINDOW_DAYS, max(1, int(window_days or 30)))
        checked, with_ba, with_rid, with_ip, distinct_actors = self.repo.bounds(window_days)

        rows = self.repo.recent(sample_limit, window_days=window_days)
        identities = self.repo.actor_identities([row.user_id for row in rows])
        violations: List[Dict[str, Any]] = []
        unresolved = 0
        redaction_markers = 0

        for row in rows:
            if not row.action:
                violations.append({"row_id": row.id, "issue": "missing_action"})
            if row.timestamp is None:
                violations.append({"row_id": row.id, "issue": "missing_timestamp"})
            if row.user_id is not None and row.user_id not in identities:
                unresolved += 1
            payload = {
                "details": row.details_json,
                "before": _loads(row.before_json),
                "after": _loads(row.after_json),
            }
            if contains_secret(payload):
                # The scrubber runs on the write path; a hit here means a row
                # predates it or bypassed it. Surface it, never mask it here.
                violations.append({"row_id": row.id, "issue": "unredacted_secret_in_payload", "action": row.action})
            blob = " ".join(filter(None, [row.details_json, row.before_json, row.after_json]))
            if REDACTED_PREFIX in blob:
                redaction_markers += 1

        verdict = "ok" if not violations else "violations_found"
        if checked == 0:
            verdict = "no_data"
        return {
            "checked_rows": checked,
            "window_days": window_days,
            "sampled_rows": len(rows),
            "violations": violations[:100],
            "unresolved_actors": unresolved,
            "redaction_markers": redaction_markers,
            "rows_with_before_after": with_ba,
            "rows_with_request_id": with_rid,
            "rows_with_ip": with_ip,
            "distinct_actors": distinct_actors,
            "verdict": verdict,
            "tamper_evident": False,
            "limitations": [
                "Not tamper-evident: audit_logs has no persisted hash chain, so a "
                "writer with direct database access could alter historical rows "
                "undetected. Closing this requires a schema migration.",
                f"Sampled at most {sample_limit} of {checked} rows in the window.",
                "Retention/deletion policy is not enforced by the application; rows "
                "are append-only by convention only.",
            ],
        }
