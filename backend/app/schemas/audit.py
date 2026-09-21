"""Pydantic contracts for the platform audit trail.

Pinned as explicit models (rather than ``Dict[str, Any]``) because the audit
trail is a compliance surface: its wire shape must not drift silently between
what the backend emits and what the admin UI renders. That is exactly how
G-04 happened on the heatmaps.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AuditEntryOut(BaseModel):
    """One audit row, fully enriched.

    ``before`` / ``after`` / ``request_id`` / ``ip_address`` are the columns
    migration ``0017_audit_before_after_request_id`` added; the previous
    endpoint dropped all four, which made the trail unable to answer *what
    changed*, *which request did it* and *from where* (G-05).
    """

    id: int
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    actor: str
    actor_id: Optional[int] = None
    actor_email: Optional[str] = None
    actor_role: Optional[str] = None
    ip_address: Optional[str] = None
    request_id: Optional[str] = None
    details: Optional[str] = None
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None
    changed_fields: List[str] = Field(default_factory=list)
    timestamp: Optional[datetime] = None

    model_config = ConfigDict(extra="allow")


class AuditPageMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    has_previous: bool


class AuditTrailPage(BaseModel):
    """Paginated audit trail envelope."""

    items: List[AuditEntryOut]
    meta: AuditPageMeta
    filters: Dict[str, Any] = Field(default_factory=dict)
    facets: Optional[Dict[str, Any]] = None
    request_id: Optional[str] = None
    methodology: str = (
        "Every row is a real audit_logs record written by the platform's own "
        "write path (UserRepository.log_audit). before/after carry the "
        "resource state either side of the action with secret-bearing fields "
        "replaced by [REDACTED:key=...]; request_id is the X-Request-Id of the "
        "HTTP request that produced the row. No rows are synthesised: an empty "
        "trail is returned empty."
    )


class AuditFacetValue(BaseModel):
    value: str
    count: int
    # Actor facets carry the identity behind the label so the UI can build a
    # working ``actor_id`` filter without a second round trip.
    actor_id: Optional[int] = None
    role: Optional[str] = None


class AuditFacetsOut(BaseModel):
    """Filter vocabulary for the admin audit UI, derived from real rows."""

    actions: List[AuditFacetValue]
    resource_types: List[AuditFacetValue]
    actors: List[AuditFacetValue]
    oldest: Optional[datetime] = None
    newest: Optional[datetime] = None


class AuditStatsOut(BaseModel):
    """Governance rollup: who did what, how often, over what window."""

    window_days: int
    total_events: int
    by_action: List[AuditFacetValue]
    by_resource_type: List[AuditFacetValue]
    by_actor: List[AuditFacetValue]
    by_day: List[Dict[str, Any]]
    distinct_actors: int
    admin_action_events: int
    methodology: str = (
        "COUNT/GROUP BY over audit_logs, restricted to the requested window. "
        "admin_action_events counts actions in the ADMIN_* namespace, i.e. the "
        "privileged surface. Empty groups are omitted rather than zero-filled."
    )


class AuditIntegrityOut(BaseModel):
    """Structural self-check of the audit table.

    This is an honest, bounded check — it verifies the invariants the write
    path actually guarantees (required columns populated, ordering, actor
    resolvable, redaction applied) and reports what it could not check. It
    does **not** claim tamper-evidence: that would require a persisted hash
    chain, which needs a schema migration this branch deliberately does not
    introduce (see the gap register).
    """

    checked_rows: int
    window_days: int
    violations: List[Dict[str, Any]]
    unresolved_actors: int
    redaction_markers: int
    rows_with_before_after: int
    rows_with_request_id: int
    rows_with_ip: int
    verdict: str
    tamper_evident: bool = False
    limitations: List[str] = Field(default_factory=list)
