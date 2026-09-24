"""Audit-trail policy layer (G-05, G-06).

Sits between the controller and ``AuditRepository`` and owns the decisions that
are *policy* rather than *data*: pagination caps, actor enrichment, the
before/after diff, the integrity self-check and its honest limitations.

Layering follows the rest of the backend (controller → service → repository →
SQLAlchemy) so the same policy is applied no matter which endpoint asks.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("confit.audit.integrity")

from sqlalchemy import func
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
    def integrity(
        self,
        window_days: int = 30,
        sample_limit: int = 500,
        actor_id: Optional[int] = None,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Structural self-check + hash-chain verification over real rows.

        Returns concrete violations rather than a boolean, because "the audit
        log is fine" is exactly the kind of unverifiable claim this feature is
        supposed to eliminate.

        Since migration 0020 every insert carries an HMAC-SHA256 hash chain
        (core/audit_chain.py), so this check now RECOMPUTES the chain over the
        sampled rows: a modified row fails its own HMAC, a deleted or
        reordered row breaks the linkage of its successor. ``tamper_evident``
        is true only when chained rows exist and the chain verifies — never
        asserted from configuration alone.
        """
        from backend.app.core.audit_chain import GENESIS_HASH, verify_chain
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

        # Chain verification runs in ascending id order (oldest → newest);
        # ``recent`` returns newest-first, so reverse the same sample.
        from backend.app.models.user import AuditLog as _AuditLog

        ordered = list(reversed(rows))

        # Anchor the window's first chained row against its ACTUAL database
        # predecessor, not against whatever the row itself claims: without
        # this, deleting rows just before the window (or the entire earlier
        # chain) is invisible to a window-scoped check. If no chained
        # predecessor exists, the first chained row must anchor to GENESIS.
        expected_prev = None
        first_chained = next((r for r in ordered if r.entry_hash is not None), None)
        if first_chained is not None:
            predecessor = (
                self.db.query(_AuditLog.entry_hash)
                .filter(_AuditLog.entry_hash.isnot(None), _AuditLog.id < first_chained.id)
                .order_by(_AuditLog.id.desc())
                .first()
            )
            expected_prev = predecessor[0] if predecessor else GENESIS_HASH

        chain = verify_chain(ordered, expected_prev=expected_prev)
        for broken in chain["breaks"]:
            violations.append(
                {"row_id": broken["row_id"], "issue": broken["issue"], "detail": broken["detail"]}
            )

        # Unchained rows are only "legacy" if they predate the first chained
        # row. An unchained row WRITTEN AFTER chaining began means some write
        # path bypassed the mapper listener — that is a finding, not history.
        # Checked globally (not just the sample) so a bypass can't hide
        # outside the sampled window.
        min_chained_id = (
            self.db.query(func.min(_AuditLog.id))
            .filter(_AuditLog.entry_hash.isnot(None))
            .scalar()
        )
        bypass_suspected_rows = 0
        if min_chained_id is not None:
            bypass_suspected_rows = int(
                self.db.query(func.count(_AuditLog.id))
                .filter(_AuditLog.entry_hash.is_(None), _AuditLog.id > min_chained_id)
                .scalar() or 0
            )
            if bypass_suspected_rows:
                violations.append({
                    "row_id": None,
                    "issue": "chain_bypass_suspected",
                    "detail": f"{bypass_suspected_rows} unchained row(s) have ids AFTER the "
                              f"first chained row (id={min_chained_id}) — they were written "
                              "through a path that skipped the hash-chain listener, or their "
                              "hashes were nulled. Legacy rows cannot appear there.",
                })

        # Tail-truncation detection across runs (0021): the head recorded by
        # the PREVIOUS verification run must still exist in audit_logs. If it
        # does not, the newest rows were deleted after that run — the one
        # attack single-run chain verification cannot see.
        from backend.app.models.user import AuditLog, AuditVerificationRun

        truncation_check: Dict[str, Any] = {"previous_run": None, "verdict": "no_prior_run"}
        prior = (
            self.db.query(AuditVerificationRun)
            .order_by(AuditVerificationRun.id.desc())
            .first()
        )
        if prior is not None:
            truncation_check["previous_run"] = {
                "run_at": prior.run_at,
                "head_row_id": prior.head_row_id,
                "head_hash": prior.head_hash,
            }
            if prior.head_hash:
                still_there = (
                    self.db.query(AuditLog.id)
                    .filter(AuditLog.id == prior.head_row_id,
                            AuditLog.entry_hash == prior.head_hash)
                    .first()
                )
                if still_there:
                    truncation_check["verdict"] = "anchored"
                else:
                    truncation_check["verdict"] = "tail_truncation_detected"
                    violations.append({
                        "row_id": prior.head_row_id,
                        "issue": "tail_truncation_detected",
                        "detail": "The chain head recorded by the previous "
                                  "verification run no longer exists in "
                                  "audit_logs — rows were deleted after "
                                  f"{prior.run_at}.",
                    })
            else:
                truncation_check["verdict"] = "prior_run_had_no_head"

        chained_rows = int(chain["rows_verified"])
        tamper_evident = (
            chained_rows > 0
            and not chain["breaks"]
            and truncation_check["verdict"] != "tail_truncation_detected"
        )

        # The anchor for the NEXT run is the newest chained row globally
        # (not window-scoped — truncation of any tail must be visible even
        # if the window has since moved past it).
        global_head = (
            self.db.query(AuditLog.id, AuditLog.entry_hash)
            .filter(AuditLog.entry_hash.isnot(None))
            .order_by(AuditLog.id.desc())
            .first()
        )

        verdict = "ok" if not violations else "violations_found"
        if checked == 0:
            verdict = "no_data"

        if verdict == "violations_found":
            # Structured, secret-free operational signal: issue kinds and
            # counts only — never row payloads, hashes or key material. This
            # is what alerting hooks into (see incident runbook §4).
            issue_counts: Dict[str, int] = {}
            for violation in violations:
                issue_counts[violation["issue"]] = issue_counts.get(violation["issue"], 0) + 1
            logger.warning(
                "audit integrity violations detected",
                extra={
                    "audit_verdict": verdict,
                    "audit_issue_counts": issue_counts,
                    "audit_window_days": window_days,
                    "audit_sampled_rows": len(rows),
                    "audit_bypass_suspected_rows": bypass_suspected_rows,
                    "audit_truncation_verdict": truncation_check["verdict"],
                },
            )

        limitations = [
            f"Sampled at most {sample_limit} of {checked} rows in the window; the "
            "chain is verified over that sample in id order.",
            "Chain HMAC uses a dedicated AUDIT_HMAC_KEY (separate from the JWT "
            "key); an attacker holding BOTH direct DB write access AND that key "
            "could re-forge the chain forward from the tampered point. External "
            "anchoring (WORM/signed Merkle roots) is the documented next step.",
            "Tail truncation is detected ACROSS runs via the persisted head of "
            "the previous verification run (audit_verification_runs); a first "
            "run has no prior anchor and says so.",
        ]
        if chain["unchained_rows"]:
            limitations.append(
                f"{chain['unchained_rows']} sampled row(s) carry no hash. Rows "
                "older than the first chained row are legacy (pre-0020) and are "
                "never silently re-signed; unchained rows NEWER than that are "
                "flagged as chain_bypass_suspected, not excused as legacy."
            )

        result = {
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
            "tamper_evident": tamper_evident,
            # Explicit coverage semantics: what this check DID and DID NOT
            # look at, machine-readable so no UI can imply a full-history
            # guarantee that a window sample cannot give.
            "coverage": {
                "mode": "window_sample",
                "window_days": window_days,
                "sample_limit": sample_limit,
                "sampled_rows": len(rows),
                "rows_in_window": checked,
                "window_anchored_to_predecessor": expected_prev is not None,
                "full_history": False,
                "full_history_procedure": "backend/scripts/verify_audit_chain.py "
                                          "(deliberate offline run; never per-request)",
            },
            "chain": {
                "chained_rows": chained_rows,
                "unchained_rows": chain["unchained_rows"],
                "first_chained_row_id": min_chained_id,
                "bypass_suspected_rows": bypass_suspected_rows,
                "breaks": chain["breaks"][:50],
                "head_hash": chain["head_hash"],
                "key_version": chain["key_version"],
                "canonical_version": chain["canonical_version"],
            },
            "truncation_check": truncation_check,
            "limitations": limitations,
        }

        # Record this run as an immutable event (0021) so the NEXT run can
        # detect tail truncation. Written after the result is composed so a
        # failure to persist the run can never alter the verdict; it would
        # surface as an exception, not a silently different answer.
        self.db.add(
            AuditVerificationRun(
                window_days=window_days,
                checked_rows=checked,
                sampled_rows=len(rows),
                chained_rows=chained_rows,
                unchained_rows=int(chain["unchained_rows"]),
                break_count=len(chain["breaks"]),
                verdict=verdict,
                tamper_evident=tamper_evident,
                head_hash=global_head[1] if global_head else None,
                head_row_id=global_head[0] if global_head else None,
                key_version=int(chain["key_version"]),
                canonical_version=int(chain["canonical_version"]),
                triggered_by_user_id=actor_id,
                request_id=request_id,
            )
        )
        self.db.commit()
        return result
