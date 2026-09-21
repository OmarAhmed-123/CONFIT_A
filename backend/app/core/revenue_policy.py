"""One vocabulary for the question "does this order count as revenue?".

Why this module exists (gap G-13)
---------------------------------
The admin dashboard computed GMV with ``status NOT IN ('cancelled','refunded')``
while the item-grain attribution ledger — rendered on the same screen, next to
the same total — used ``status NOT IN ('cancelled','refunded','failed')``. Two
hand-written denylists, two populations, one number pair the reader was invited
to compare. A payment-failed order was inside GMV and outside the attribution
base, so the four channel figures could never sum to the headline.

The deeper problem is the shape of the fix, not the missing string: a denylist
written inline at each call site silently classifies *every future state* as
revenue. ``ORDER_TRANSITIONS`` in ``commerce_service`` owns 22 states today;
adding a 23rd would have made it revenue in five places at once, with no test
failing.

So the classification lives here, once, as a **partition** of the state machine:
every state is assigned to exactly one bucket, and
``unclassified_states()`` lets a test assert the partition still covers the
machine. Adding a state without classifying it now fails CI instead of quietly
inflating GMV.

Accounting basis
----------------
Revenue-standing is an **accrual** reading: an order counts when the platform
has taken the money and not given it back. ``payment_pending``, ``placed`` and
the fulfilment states therefore count. That is a deliberate, stated choice —
not an oversight — and it is surfaced in the API payload as ``revenue_basis``
so a reader knows which question the number answers. Cash-basis GMV would
exclude ``payment_pending``; if that is ever wanted, it is a new bucket here,
not a new literal at a call site.

Nothing in this module imports SQLAlchemy models: the helpers take the status
*column* they should filter, which keeps ``core`` free of ORM imports and lets
the same predicate serve ``Order.status`` today and any future status column.
"""

from typing import FrozenSet, Iterable, List

__all__ = [
    "NON_REVENUE_ORDER_STATUSES",
    "RETURN_IN_FLIGHT_ORDER_STATUSES",
    "RETURN_DENOMINATOR_EXCLUDED_STATUSES",
    "REVENUE_BASIS",
    "classify_order_status",
    "unclassified_states",
    "revenue_eligible",
    "return_denominator_eligible",
]

#: Money did not stay with the platform and no goods were kept.
#:
#: * ``cancelled`` — order voided before fulfilment.
#: * ``failed`` — payment failed, inventory released, nothing was ever owed.
#: * ``refunded`` — money returned to the customer.
NON_REVENUE_ORDER_STATUSES: FrozenSet[str] = frozenset({"cancelled", "failed", "refunded"})

#: Revenue stands, but the goods are (or may yet be) coming back.
#:
#: ``rejected`` is included on purpose: per ``ORDER_TRANSITIONS`` it is the
#: terminal state of a *rejected return*, i.e. the goods were delivered and
#: kept, so the revenue is real — it is listed here only because it belongs to
#: the returns conversation, not because it is doubtful.
RETURN_IN_FLIGHT_ORDER_STATUSES: FrozenSet[str] = frozenset(
    {
        "return_requested",
        "partially_returned",
        "returned",
        "refund_pending",
        "refund_failed",
        "exchange_requested",
        "rejected",
        "failed_delivery",
    }
)

#: States excluded from the **denominator of a return rate**.
#:
#: Deliberately *not* the same set as :data:`NON_REVENUE_ORDER_STATUSES`, and
#: the difference is the whole point. ``refunded`` is excluded from revenue
#: (the money went back) but must stay in the return-rate denominator: a return
#: that succeeded is the strongest possible evidence of a return. Excluding it
#: would make the return rate fall exactly when returns work — the metric would
#: reward the outcome it exists to measure.
RETURN_DENOMINATOR_EXCLUDED_STATUSES: FrozenSet[str] = frozenset({"cancelled", "failed"})

REVENUE_BASIS = "accrual"

#: Revenue-standing states that are not part of the returns conversation.
#: Listed explicitly (rather than as "everything else") so the partition is
#: closed and ``unclassified_states`` can prove it covers the state machine.
_KNOWN_REVENUE_STATUSES: FrozenSet[str] = frozenset(
    {
        "placed",
        "payment_pending",
        "processing",
        "preparing",
        "ready_for_pickup",
        "dispatched",
        "shipped",
        "out_for_delivery",
        "delivered",
        "picked_up",
        "completed",
    }
)

_BUCKET_NON_REVENUE = "non_revenue"
_BUCKET_RETURN_IN_FLIGHT = "return_in_flight"
_BUCKET_REVENUE = "revenue"


def classify_order_status(status: str) -> str:
    """Return the bucket a single order status belongs to.

    Raises ``ValueError`` for an unknown status rather than defaulting to
    revenue — the failure mode this module exists to prevent.
    """
    if status in NON_REVENUE_ORDER_STATUSES:
        return _BUCKET_NON_REVENUE
    if status in RETURN_IN_FLIGHT_ORDER_STATUSES:
        return _BUCKET_RETURN_IN_FLIGHT
    if status in _KNOWN_REVENUE_STATUSES:
        return _BUCKET_REVENUE
    raise ValueError(
        f"Order status {status!r} is not classified in revenue_policy. "
        "Add it to the correct bucket; do not let it default to revenue."
    )


def unclassified_states(known_states: Iterable[str]) -> List[str]:
    """States in ``known_states`` that no bucket claims.

    Intended to be fed ``ORDER_TRANSITIONS`` by a test, so growing the state
    machine without classifying the new state fails CI.
    """
    classified = (
        NON_REVENUE_ORDER_STATUSES
        | RETURN_IN_FLIGHT_ORDER_STATUSES
        | _KNOWN_REVENUE_STATUSES
        | RETURN_DENOMINATOR_EXCLUDED_STATUSES
    )
    return sorted({s for s in known_states if s not in classified})


def revenue_eligible(status_column):
    """SQL predicate: this order counts towards revenue.

    Every GMV, revenue and attribution figure must filter with this and only
    this, so the headline and its breakdown measure the same population.
    """
    return status_column.notin_(sorted(NON_REVENUE_ORDER_STATUSES))


def return_denominator_eligible(status_column):
    """SQL predicate: this order belongs in a return-rate denominator."""
    return status_column.notin_(sorted(RETURN_DENOMINATOR_EXCLUDED_STATUSES))
