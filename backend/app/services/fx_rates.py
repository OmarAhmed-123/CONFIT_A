"""Live foreign-exchange rates — one cached, fail-safe rate table.

WHY THIS EXISTS
---------------
Until now the FX table was a hand-maintained JSON blob in ``MARKET_FX_RATES``.
That has two failure modes that both end in mispriced money:

1. It goes stale silently. EGP moved from ~48.5 to ~52.09 during this project;
   a storefront quoting a months-old rate under-charges or over-charges on
   every order and nothing in the system notices.
2. It only covers the currencies someone remembered to type. A shopper outside
   the eight registry markets had no option at all.

This module fetches real rates from exchangerate-api's open endpoint (no key,
166 currencies, documented daily refresh) and caches them in-process.

DESIGN CONSTRAINTS THAT SHAPED IT
---------------------------------
* **It must never take checkout down.** Money resolution is on the critical
  path, so every failure mode degrades instead of raising: live → last good
  snapshot (even past TTL) → the configured static table → empty. An empty
  table is itself handled upstream by settling in the price-book currency.
* **One table for display AND settlement.** ``MarketSettlement.fx_rates()``
  reads THIS provider, so the number a shopper sees and the number they are
  charged come from the same snapshot. Two rate sources is precisely how a
  storefront ends up disagreeing with its own checkout — a class of bug this
  project has already paid for once.
* **Serverless-aware.** Vercel gives us short-lived containers, so the cache is
  per-process with a long TTL and a hard 3-second timeout. A cold container
  pays one fetch; every later request in that container is free. It never
  blocks longer than the timeout, and a timeout is not an error path for the
  caller.
* **Hermetic tests.** Honouring ``CONFIT_IGNORE_DOTENV`` (the repository's
  existing test contract, also used by the NVIDIA key pool) means pytest never
  makes a real network call for rates. A rate loader that ignores the test
  contract is a rate loader that will eventually make CI depend on an external
  vendor's uptime.

HONESTY
-------
``snapshot().source`` always states where the numbers came from —
``live``, ``stale_live``, ``configured`` or ``unavailable`` — and ``as_of``
states when. A rate with no provenance is a rate nobody can audit.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Dict, Optional

from backend.app.core.config import settings
from backend.app.core.logging import logger

#: exchangerate-api's open endpoint. No API key, no per-request quota for the
#: open tier, 166 currencies, ``time_next_update_utc`` published in the body.
DEFAULT_ENDPOINT = "https://open.er-api.com/v6/latest/{base}"

#: 6 hours. The upstream refreshes daily, so anything shorter only adds
#: latency to cold containers without improving accuracy.
DEFAULT_TTL_SECONDS = 6 * 60 * 60

#: Hard ceiling on the outbound call. Checkout latency budget, not patience.
DEFAULT_TIMEOUT_SECONDS = 3.0


@dataclass(frozen=True)
class RateSnapshot:
    """An immutable rate table plus its provenance."""

    base: str
    rates: Dict[str, Decimal] = field(default_factory=dict)
    #: ``live`` | ``stale_live`` | ``configured`` | ``unavailable``
    source: str = "unavailable"
    #: Upstream publication time, or ``None`` for the configured table.
    as_of: Optional[str] = None
    next_update: Optional[str] = None
    fetched_at: float = 0.0

    @property
    def is_empty(self) -> bool:
        return not self.rates

    def meta(self) -> Dict[str, Optional[str]]:
        return {
            "base": self.base,
            "source": self.source,
            "as_of": self.as_of,
            "next_update": self.next_update,
            "currencies": str(len(self.rates)),
        }


def _parse_rate_table(raw: object, context: str) -> Dict[str, Decimal]:
    """Parse ``{code: rate}`` defensively.

    A malformed table must never take money resolution down, and a malformed
    ENTRY must never be silently treated as 1.0 — that would mislabel money
    rather than merely fail. Bad entries are dropped and logged.
    """
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            raw = json.loads(text)
        except (TypeError, ValueError) as exc:
            logger.error("fx_rate_table_unparseable", context=context,
                         error=f"{type(exc).__name__}: {exc}"[:200])
            return {}
    if not isinstance(raw, dict):
        logger.error("fx_rate_table_wrong_shape", context=context, got=type(raw).__name__)
        return {}

    out: Dict[str, Decimal] = {}
    for key, value in raw.items():
        code = str(key).strip().upper()
        if not code.isalpha() or len(code) != 3:
            continue
        try:
            rate = Decimal(str(value).strip())
        except (InvalidOperation, AttributeError, TypeError, ValueError):
            logger.error("fx_rate_invalid", context=context, currency=code, value=str(value)[:40])
            continue
        if not rate.is_finite() or rate <= 0:
            logger.error("fx_rate_non_positive", context=context, currency=code, value=str(rate))
            continue
        out[code] = rate
    return out


class FxRateProvider:
    """Thread-safe, cached, fail-safe rate table.

    One process-wide instance (``fx_rates`` below). Callers ask for a
    ``snapshot()``; they never trigger an unbounded fetch and never see an
    exception from this layer.
    """

    def __init__(self, endpoint: str = DEFAULT_ENDPOINT) -> None:
        self._endpoint = endpoint
        self._lock = threading.Lock()
        self._cached: Optional[RateSnapshot] = None
        #: Set after a failure so a dead upstream is not re-dialled on every
        #: request. Without it a 3s timeout would be paid per request during
        #: an outage — turning a vendor problem into our latency problem.
        self._retry_not_before: float = 0.0

    # ── configuration ────────────────────────────────────────────────────────

    @staticmethod
    def _live_enabled() -> bool:
        if os.environ.get("CONFIT_IGNORE_DOTENV") == "1":
            # Hermetic test contract: no outbound calls from pytest.
            return False
        return bool(getattr(settings, "FX_LIVE_RATES_ENABLED", True))

    @staticmethod
    def _ttl() -> int:
        try:
            return max(60, int(getattr(settings, "FX_RATE_TTL_SECONDS", DEFAULT_TTL_SECONDS)))
        except (TypeError, ValueError):
            return DEFAULT_TTL_SECONDS

    @staticmethod
    def _base() -> str:
        raw = (getattr(settings, "PRICING_CURRENCY", "") or "").strip().upper()
        return raw or "USD"

    @staticmethod
    def _configured() -> Dict[str, Decimal]:
        return _parse_rate_table(getattr(settings, "MARKET_FX_RATES", "") or "", "MARKET_FX_RATES")

    # ── public surface ───────────────────────────────────────────────────────

    def snapshot(self) -> RateSnapshot:
        """The current rate table. Never raises, never blocks past the timeout."""
        base = self._base()
        now = time.monotonic()

        with self._lock:
            cached = self._cached
            fresh = (
                cached is not None
                and cached.base == base
                and cached.source in ("live", "stale_live")
                and (now - cached.fetched_at) < self._ttl()
            )
            if fresh:
                return cached  # type: ignore[return-value]
            may_retry = now >= self._retry_not_before

        if self._live_enabled() and may_retry:
            fetched = self._fetch(base)
            if fetched is not None:
                with self._lock:
                    self._cached = fetched
                    self._retry_not_before = 0.0
                return fetched
            with self._lock:
                # Back off for one TTL slice before dialling a dead upstream again.
                self._retry_not_before = time.monotonic() + min(300, self._ttl())

        # Degrade, in order of trustworthiness.
        with self._lock:
            cached = self._cached
        if cached is not None and cached.base == base and not cached.is_empty:
            # Stale live numbers beat no numbers: they were real once, and the
            # source string says so out loud.
            return RateSnapshot(
                base=cached.base, rates=cached.rates, source="stale_live",
                as_of=cached.as_of, next_update=cached.next_update,
                fetched_at=cached.fetched_at,
            )

        configured = self._configured()
        if configured:
            return RateSnapshot(base=base, rates=configured, source="configured")
        return RateSnapshot(base=base, rates={}, source="unavailable")

    def rates(self) -> Dict[str, Decimal]:
        """Just the table — the common case for callers that do not report
        provenance (``MarketSettlement.fx_rates``)."""
        return dict(self.snapshot().rates)

    def invalidate(self) -> None:
        """Drop the cache. Used by tests and by an operator forcing a refresh."""
        with self._lock:
            self._cached = None
            self._retry_not_before = 0.0

    # ── internals ────────────────────────────────────────────────────────────

    def _fetch(self, base: str) -> Optional[RateSnapshot]:
        try:
            import httpx

            url = self._endpoint.format(base=base)
            with httpx.Client(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
                response = client.get(url, headers={"Accept": "application/json"})
                response.raise_for_status()
                body = response.json()
        except Exception as exc:  # noqa: BLE001 - a rate fetch must never propagate
            logger.warning(
                "fx_live_rates_unavailable",
                base=base,
                error=f"{type(exc).__name__}: {exc}"[:200],
                note="falling back to the last good snapshot, then MARKET_FX_RATES",
            )
            return None

        if not isinstance(body, dict) or body.get("result") != "success":
            logger.warning("fx_live_rates_rejected", base=base,
                           result=str(body.get("result") if isinstance(body, dict) else body)[:80])
            return None

        table = _parse_rate_table(body.get("rates"), "live")
        # The base must be present and exactly 1, otherwise the payload is not
        # denominated the way we asked and every conversion would be skewed.
        if not table or table.get(body.get("base_code", base).upper()) != Decimal("1"):
            logger.warning("fx_live_rates_base_mismatch", base=base,
                           base_code=str(body.get("base_code"))[:10], size=len(table))
            return None

        snapshot = RateSnapshot(
            base=base,
            rates=table,
            source="live",
            as_of=body.get("time_last_update_utc"),
            next_update=body.get("time_next_update_utc"),
            fetched_at=time.monotonic(),
        )
        logger.info("fx_live_rates_refreshed", base=base, currencies=len(table),
                    as_of=snapshot.as_of)
        return snapshot


#: Process-wide provider. Import this; do not build your own, or the cache
#: (and therefore the rate every request sees) fragments.
fx_rates = FxRateProvider()
