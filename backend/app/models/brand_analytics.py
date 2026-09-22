from datetime import datetime, timezone
from sqlalchemy import (Column, Integer, String, DateTime, Date, Boolean, ForeignKey, Text,
                        Float, Numeric, CheckConstraint, UniqueConstraint, Index)
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class SponsoredPlacement(Base):
    __tablename__ = "sponsored_placements"
    __table_args__ = (
        CheckConstraint("bid_amount_per_click > 0", name="ck_sponsored_bid_positive"),
        CheckConstraint("daily_budget > 0", name="ck_sponsored_budget_positive"),
        CheckConstraint("bid_amount_per_click <= daily_budget", name="ck_sponsored_bid_lte_budget"),
        CheckConstraint("bid_amount_per_click <= 100", name="ck_sponsored_bid_max"),
        CheckConstraint("daily_budget <= 10000", name="ck_sponsored_budget_max"),
        CheckConstraint("spent_today >= 0", name="ck_sponsored_spent_nonneg"),
        CheckConstraint("spent_today <= daily_budget", name="ck_sponsored_spent_lte_budget"),
        CheckConstraint("impressions >= 0", name="ck_sponsored_impressions_nonneg"),
        CheckConstraint("clicks >= 0", name="ck_sponsored_clicks_nonneg"),
        CheckConstraint("conversions >= 0", name="ck_sponsored_conversions_nonneg"),
        CheckConstraint("revenue_generated >= 0", name="ck_sponsored_revenue_nonneg"),
        CheckConstraint("status IN ('active','paused','budget_exhausted','completed','cancelled')", name="ck_sponsored_status_valid"),
    )

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brand_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    placement_type = Column(String(50), default="stylist_featured", nullable=False, index=True) # "stylist_featured", "trending_hero", "fit_recom_top"
    bid_amount_per_click = Column(Numeric(12, 2), default=0.50, nullable=False)
    daily_budget = Column(Numeric(12, 2), default=50.0, nullable=False)
    spent_today = Column(Numeric(12, 2), default=0.0, nullable=False)
    status = Column(String(20), default="active", nullable=False, index=True) # "active", "paused", "budget_exhausted"

    impressions = Column(Integer, default=0, nullable=False)
    clicks = Column(Integer, default=0, nullable=False)
    conversions = Column(Integer, default=0, nullable=False)
    revenue_generated = Column(Numeric(12, 2), default=0.0, nullable=False)

    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)

    # Daily-budget accounting window. `spent_today` is meaningless without
    # knowing WHICH day it belongs to: before this column the counter was
    # never reset, so a placement that exhausted its budget once stayed
    # "budget_exhausted" forever and a brand's daily budget silently became a
    # lifetime budget. `spend_date` is the UTC date `spent_today` accumulates
    # against; the service rolls it over lazily on first touch of a new day.
    spend_date = Column(Date, nullable=True, index=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    brand = relationship("BrandProfile", back_populates="sponsored_placements")
    product = relationship("Product", back_populates="sponsored_placements")
    ledger_entries = relationship("AdLedgerEntry", back_populates="placement",
                                  cascade="all, delete-orphan", passive_deletes=True)


class AdLedgerEntry(Base):
    """Append-only, double-entry-style billing ledger for sponsored placements.

    WHY THIS EXISTS (audit P1 — "counters are not a billing ledger"):
    `SponsoredPlacement.impressions/clicks/spent_today` are mutable running
    counters. A counter cannot answer "why was this brand charged $37.50 on
    2026-09-21?", cannot be reconciled, cannot be audited, and silently loses
    history on every daily reset. Money needs an immutable journal.

    Design:
      * APPEND-ONLY. Rows are never updated or deleted. A correction is a new
        compensating row (`entry_type='adjustment'`) referencing the original.
      * IDEMPOTENT. `event_key` is UNIQUE: a retried/duplicated click delivery
        collides on the key and is rejected instead of double-charging. This is
        the standard exactly-once-effect pattern for billing over an at-least-
        once transport.
      * IMMUTABLE MONEY FACTS. `amount` is the charge at the moment of the
        event and `bid_at_event` snapshots the rate used, so re-pricing a
        placement later can never retroactively rewrite historical spend.
      * RECONCILABLE. SUM(amount) per (placement, spend_date) must equal
        `spent_today` for that day. `verify_placement_reconciliation()` asserts
        it and the reconciliation test fails the build if they diverge.
    """
    __tablename__ = "ad_ledger_entries"
    __table_args__ = (
        UniqueConstraint("event_key", name="uq_ad_ledger_event_key"),
        CheckConstraint("amount >= 0", name="ck_ad_ledger_amount_nonneg"),
        CheckConstraint("entry_type IN ('impression','click','conversion','adjustment')",
                        name="ck_ad_ledger_entry_type_valid"),
        Index("ix_ad_ledger_placement_date", "placement_id", "spend_date"),
        Index("ix_ad_ledger_brand_date", "brand_id", "spend_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    placement_id = Column(Integer, ForeignKey("sponsored_placements.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    brand_id = Column(Integer, ForeignKey("brand_profiles.id", ondelete="CASCADE"),
                      nullable=False, index=True)
    entry_type = Column(String(20), nullable=False, index=True)
    # Idempotency key for the billable event (caller-supplied or derived).
    # UNIQUE -> a duplicate delivery can never be charged twice.
    event_key = Column(String(128), nullable=False)
    amount = Column(Numeric(12, 2), default=0, nullable=False)
    bid_at_event = Column(Numeric(12, 2), nullable=True)
    spend_date = Column(Date, nullable=False, index=True)
    # Fraud/abuse forensics: who/where the billable event came from.
    actor_user_id = Column(Integer, nullable=True, index=True)
    ip_hash = Column(String(64), nullable=True, index=True)
    user_agent = Column(String(300), nullable=True)
    request_id = Column(String(64), nullable=True)
    # Set when the event was recorded but deliberately NOT charged
    # (e.g. deduplicated click within the fraud window). Keeps the audit
    # trail complete instead of dropping the event on the floor.
    billable = Column(Boolean, default=True, nullable=False)
    reason = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    placement = relationship("SponsoredPlacement", back_populates="ledger_entries")


class StyleHeatmapAggregate(Base):
    __tablename__ = "style_heatmap_aggregates"

    id = Column(Integer, primary_key=True, index=True)
    period = Column(String(50), default="monthly", nullable=False)  # "weekly", "monthly", "quarterly"
    region = Column(String(100), default="MENA", nullable=False)    # "MENA", "GCC", "Global"
    top_aesthetics_json = Column(Text, nullable=False)              # JSON: [{"name":"Old Money", "weight":35}, ...]
    top_colors_json = Column(Text, nullable=False)                  # JSON: [{"color":"Navy", "hex":"#1B1F3B", "weight":42}, ...]
    top_occasions_json = Column(Text, nullable=False)               # JSON: [{"name":"Smart Casual Work", "weight":48}, ...]
    sample_size = Column(Integer, default=12500, nullable=False)
    calculated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
