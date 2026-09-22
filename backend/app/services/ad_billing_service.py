"""Sponsored-placement billing: ledger, daily budget windows and fraud controls.

AUDIT CONTEXT (P1 — "placements prove settings persistence, not ad delivery or
billing"). Before this module the money path for placements was three mutable
integers/decimals on the placement row:

    plc.impressions += 1
    plc.clicks += 1
    plc.spent_today = spent_today + bid

That has four defects that make it unusable as a commercial system, all of
which are fixed here:

  1. NO DAILY WINDOW. `spent_today` was never reset. The column name promised
     a day; the behaviour delivered a lifetime. A placement that hit its budget
     once stayed `budget_exhausted` forever. Fixed by `spend_date` + a lazy,
     row-locked rollover (`_roll_day`), which needs no cron and is correct even
     if a scheduler never runs.

  2. NO LEDGER. A counter cannot be reconciled, audited or disputed, and it
     loses all history at reset. Every billable event now also appends an
     immutable `AdLedgerEntry`. The counter becomes a cached projection of the
     journal; `reconcile` proves the two agree.

  3. NOT IDEMPOTENT. HTTP delivery is at-least-once; a retry double-charged the
     brand. Every event now carries a UNIQUE `event_key`, so a duplicate hits a
     unique-violation and is reported as `duplicate` — charged exactly once.

  4. NO FRAUD CONTROL. Any authenticated caller could bill clicks in a loop.
     Clicks are now deduplicated per (placement, actor/IP) inside a cooldown
     window and recorded as non-billable rather than silently dropped, so the
     audit trail stays complete.

Concurrency: every mutation takes `SELECT ... FOR UPDATE` on the placement row
before reading the budget, so two concurrent clicks cannot both observe
"budget remaining" and jointly overspend (the lost-update / double-spend race).
Budget admission is checked against the ledger-backed spend for the CURRENT day.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.money import money_add, money_sub, quantize_money
from backend.app.models.brand_analytics import AdLedgerEntry, SponsoredPlacement

logger = logging.getLogger(__name__)

ZERO = Decimal("0.00")

# A repeated click from the same actor on the same placement inside this window
# is recorded but NOT charged. Conservative, documented, and enforced in one
# place so the rule cannot drift between call sites.
CLICK_DEDUP_WINDOW_SECONDS = 60
# Impressions are far noisier than clicks; they are free (CPC model) but still
# deduplicated so impression counts are not trivially inflatable.
IMPRESSION_DEDUP_WINDOW_SECONDS = 10


class AdBillingError(Exception):
    """Business-rule rejection (not active, out of window, budget exhausted)."""

    def __init__(self, message: str, code: str = "AD_BILLING_REJECTED"):
        super().__init__(message)
        self.code = code


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def hash_ip(ip: Optional[str]) -> Optional[str]:
    """Store a salted-ish digest, never a raw IP (data-minimisation: the ledger
    is retained for accounting years, a raw IP is personal data)."""
    if not ip:
        return None
    return hashlib.sha256(f"confit-ad-ledger|{ip}".encode()).hexdigest()[:64]


class AdBillingService:
    def __init__(self, db: Session):
        self.db = db

    # ---------------- daily window ----------------

    def _roll_day(self, plc: SponsoredPlacement, today: date) -> bool:
        """Lazily start a new accounting day. Caller MUST already hold the row
        lock. Returns True if a rollover happened.

        Lazy rollover (rather than a nightly cron) is deliberate: it is correct
        on the first request of the new day even if no scheduler exists, it
        cannot double-run, and it needs no distributed lock. A placement that
        was only paused by budget exhaustion is reactivated; one a human paused
        stays paused (operator intent outranks the scheduler).
        """
        if plc.spend_date == today:
            return False
        plc.spend_date = today
        plc.spent_today = ZERO
        if plc.status == "budget_exhausted":
            plc.status = "active"
        return True

    def _spent_today(self, plc: SponsoredPlacement, today: date) -> Decimal:
        """Authoritative spend for today, read from the LEDGER (not the cached
        counter) so admission control is based on the journal of record."""
        total = (
            self.db.query(func.coalesce(func.sum(AdLedgerEntry.amount), 0))
            .filter(
                AdLedgerEntry.placement_id == plc.id,
                AdLedgerEntry.spend_date == today,
                AdLedgerEntry.billable.is_(True),
            )
            .scalar()
        )
        return quantize_money(Decimal(str(total or 0)))

    # ---------------- eligibility ----------------

    def _assert_servable(self, plc: SponsoredPlacement, now: datetime) -> None:
        if plc.status == "paused":
            raise AdBillingError("Placement is paused", "PLACEMENT_PAUSED")
        if plc.status in ("completed", "cancelled"):
            raise AdBillingError(f"Placement is {plc.status}", "PLACEMENT_CLOSED")
        if plc.start_date and now < plc.start_date:
            raise AdBillingError("Placement has not started", "PLACEMENT_NOT_STARTED")
        if plc.end_date and now > plc.end_date:
            raise AdBillingError("Placement has ended", "PLACEMENT_ENDED")

    def _recent_duplicate(self, plc_id: int, entry_type: str, actor_user_id: Optional[int],
                          ip_hash: Optional[str], window_seconds: int) -> bool:
        """True if the same actor billed the same placement within the window."""
        if actor_user_id is None and ip_hash is None:
            return False
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=window_seconds)
        q = self.db.query(AdLedgerEntry.id).filter(
            AdLedgerEntry.placement_id == plc_id,
            AdLedgerEntry.entry_type == entry_type,
            AdLedgerEntry.billable.is_(True),
            AdLedgerEntry.created_at >= cutoff,
        )
        if actor_user_id is not None:
            q = q.filter(AdLedgerEntry.actor_user_id == actor_user_id)
        else:
            q = q.filter(AdLedgerEntry.ip_hash == ip_hash)
        return self.db.query(q.exists()).scalar() is True

    # ---------------- public API ----------------

    def record_event(
        self,
        placement_id: int,
        brand_id: Optional[int],
        entry_type: str,
        *,
        event_key: Optional[str] = None,
        actor_user_id: Optional[int] = None,
        ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
        allow_any_brand: bool = False,
    ) -> Dict[str, Any]:
        """Record ONE billable placement event, exactly once.

        Ordering is deliberate: lock -> roll day -> eligibility -> fraud check
        -> budget admission -> append ledger row -> update projection -> commit.
        All of it in a single transaction, so either the journal and the
        counter both move or neither does (no torn write between money and
        its audit trail).
        """
        if entry_type not in ("impression", "click", "conversion"):
            raise AdBillingError(f"Unsupported entry type: {entry_type}", "INVALID_ENTRY_TYPE")

        q = self.db.query(SponsoredPlacement).filter(SponsoredPlacement.id == placement_id)
        if not allow_any_brand:
            q = q.filter(SponsoredPlacement.brand_id == brand_id)
        plc = q.with_for_update().first()
        if not plc:
            raise AdBillingError("Placement not found for your brand", "PLACEMENT_NOT_FOUND")

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        today = utc_today()
        self._roll_day(plc, today)
        self._assert_servable(plc, now)

        # Charge model: CPC. Impressions and conversions are recorded for
        # reporting/reconciliation but cost nothing, which is stated here
        # rather than implied by scattered arithmetic.
        charge = quantize_money(Decimal(str(plc.bid_amount_per_click))) if entry_type == "click" else ZERO
        billable = True
        reason = None

        window = CLICK_DEDUP_WINDOW_SECONDS if entry_type == "click" else IMPRESSION_DEDUP_WINDOW_SECONDS
        if entry_type in ("click", "impression") and self._recent_duplicate(
            plc.id, entry_type, actor_user_id, hash_ip(ip), window
        ):
            billable = False
            charge = ZERO
            reason = f"deduplicated: repeat {entry_type} from same actor within {window}s"

        budget = quantize_money(Decimal(str(plc.daily_budget)))
        spent = self._spent_today(plc, today)

        if billable and charge > ZERO:
            if spent + charge > budget:
                # Admission denied AND the placement is closed for the day, so
                # the next request short-circuits instead of re-querying.
                plc.status = "budget_exhausted"
                plc.spent_today = spent
                self.db.commit()
                raise AdBillingError("Daily budget would be exceeded", "BUDGET_EXHAUSTED")

        entry = AdLedgerEntry(
            placement_id=plc.id,
            brand_id=plc.brand_id,
            entry_type=entry_type,
            event_key=event_key or f"{plc.id}:{entry_type}:{now.isoformat()}:{actor_user_id or 'anon'}",
            amount=charge,
            bid_at_event=quantize_money(Decimal(str(plc.bid_amount_per_click))),
            spend_date=today,
            actor_user_id=actor_user_id,
            ip_hash=hash_ip(ip),
            user_agent=(user_agent or "")[:300] or None,
            request_id=request_id,
            billable=billable,
            reason=reason,
        )
        self.db.add(entry)

        try:
            self.db.flush()
        except IntegrityError:
            # UNIQUE(event_key) -> this exact event was already recorded. This
            # is the success path of an at-least-once retry, not an error: the
            # brand was charged exactly once.
            self.db.rollback()
            logger.info("ad_ledger duplicate event_key placement=%s type=%s", placement_id, entry_type)
            return {
                "status": "duplicate",
                "placement_id": placement_id,
                "charged": "0.00",
                "detail": "Event already recorded; not charged again (idempotent replay).",
            }

        # Projection update — the counter is now a CACHE of the ledger.
        new_spent = spent + charge
        plc.spent_today = new_spent
        if entry_type == "impression" and billable:
            plc.impressions = (plc.impressions or 0) + 1
        elif entry_type == "click" and billable:
            plc.clicks = (plc.clicks or 0) + 1
        elif entry_type == "conversion" and billable:
            plc.conversions = (plc.conversions or 0) + 1

        if new_spent >= budget:
            plc.status = "budget_exhausted"

        self.db.commit()
        self.db.refresh(plc)

        return {
            "status": "recorded" if billable else "recorded_not_billable",
            "placement_id": plc.id,
            "entry_id": entry.id,
            "entry_type": entry_type,
            "charged": str(charge),
            "billable": billable,
            "reason": reason,
            "spend_date": today.isoformat(),
            "spent_today": str(quantize_money(new_spent)),
            "daily_budget": str(budget),
            "remaining_budget": str(quantize_money(budget - new_spent)),
            "placement_status": plc.status,
            "impressions": plc.impressions,
            "clicks": plc.clicks,
        }

    # ---------------- reconciliation ----------------

    def reconcile(self, placement_id: int, on_date: Optional[date] = None) -> Dict[str, Any]:
        """Prove the cached counter equals the ledger for a given day.

        This is the control that makes the spend number defensible: if the
        projection ever drifts from the journal, `balanced` is False and the
        difference is reported instead of the discrepancy being invisible.
        """
        on_date = on_date or utc_today()
        plc = self.db.query(SponsoredPlacement).filter(SponsoredPlacement.id == placement_id).first()
        if not plc:
            raise AdBillingError("Placement not found", "PLACEMENT_NOT_FOUND")

        ledger_total = quantize_money(Decimal(str(
            self.db.query(func.coalesce(func.sum(AdLedgerEntry.amount), 0))
            .filter(AdLedgerEntry.placement_id == placement_id,
                    AdLedgerEntry.spend_date == on_date,
                    AdLedgerEntry.billable.is_(True))
            .scalar() or 0
        )))
        counter = quantize_money(Decimal(str(plc.spent_today or 0)))
        # The counter only describes the placement's CURRENT spend_date; asking
        # it about any other day is a category error, so say so explicitly.
        comparable = (plc.spend_date == on_date)
        billable_clicks = (
            self.db.query(func.count(AdLedgerEntry.id))
            .filter(AdLedgerEntry.placement_id == placement_id,
                    AdLedgerEntry.spend_date == on_date,
                    AdLedgerEntry.entry_type == "click",
                    AdLedgerEntry.billable.is_(True))
            .scalar() or 0
        )
        return {
            "placement_id": placement_id,
            "date": on_date.isoformat(),
            "ledger_total": str(ledger_total),
            "counter_spent_today": str(counter) if comparable else None,
            "comparable": comparable,
            "balanced": (ledger_total == counter) if comparable else None,
            "difference": str(quantize_money(counter - ledger_total)) if comparable else None,
            "billable_clicks": int(billable_clicks),
            "basis": "Sum of billable ad_ledger_entries.amount for the date, "
                     "compared against the placement's cached spent_today counter.",
        }

    def brand_statement(self, brand_id: int, start: date, end: date) -> Dict[str, Any]:
        """Per-day billing statement for a brand, derived ONLY from the ledger.

        This is what an invoice would be generated from — never from the
        mutable counters.
        """
        rows = (
            self.db.query(
                AdLedgerEntry.spend_date,
                AdLedgerEntry.entry_type,
                func.count(AdLedgerEntry.id),
                func.coalesce(func.sum(AdLedgerEntry.amount), 0),
            )
            .filter(AdLedgerEntry.brand_id == brand_id,
                    AdLedgerEntry.spend_date >= start,
                    AdLedgerEntry.spend_date <= end,
                    AdLedgerEntry.billable.is_(True))
            .group_by(AdLedgerEntry.spend_date, AdLedgerEntry.entry_type)
            .order_by(AdLedgerEntry.spend_date)
            .all()
        )
        days: Dict[str, Dict[str, Any]] = {}
        total = ZERO
        for spend_date, entry_type, count, amount in rows:
            key = spend_date.isoformat()
            day = days.setdefault(key, {"date": key, "impressions": 0, "clicks": 0,
                                        "conversions": 0, "amount": "0.00"})
            day[f"{entry_type}s"] = int(count)
            day["amount"] = str(quantize_money(
                Decimal(str(day["amount"])) + Decimal(str(amount or 0))))
            total = total + Decimal(str(amount or 0))
        return {
            "brand_id": brand_id,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "days": list(days.values()),
            "total_charged": str(quantize_money(total)),
            "currency": "USD",
            "basis": "Append-only ad_ledger_entries (billable only). Immutable journal of "
                     "record; placement counters are a cached projection of these rows.",
        }
