"""Lock the exchange rate onto the order, so a settled total can never be re-derived.

THE GAP
-------
`orders` already persists `total_amount`, `subtotal_amount`, the tax/shipping/
discount components and `currency`, and `order_items` persists `unit_price`
and `subtotal`. So the AMOUNTS were already locked at order creation — that
part was correct and is not what this migration changes.

What was missing is the *provenance* of those amounts. The order recorded
"EGP 9,376.57" but not "converted from a USD price book at 52.092039". Two
concrete consequences:

1. **Not auditable.** Finance could not reconstruct why an order totalled what
   it did, because the rate that produced it lived only in a 6-hour in-process
   cache (services/fx_rates.py) that is gone minutes later. Live rates made
   this strictly worse than the old static table: with a hand-edited table you
   could at least read the rate out of configuration.

2. **One refactor away from a real defect.** The presentation layer added in
   PR #241 walks `MONEY_FIELDS`, which includes `total_amount`, `unit_price`
   and `subtotal`. The day someone routes an order payload through
   `present()`, a LOCKED order would be re-converted at today's rate. The
   idempotence fix in PR #242 makes that safe only because the payload
   declares its own currency; it is still relying on a convention rather than
   on the order carrying its own arithmetic.

WHAT THIS ADDS
--------------
`orders.pricing_currency` — the denomination the price book was in when the
order was created (USD today).
`orders.fx_rate_used`     — the exact rate applied from `pricing_currency` to
`currency`, as NUMERIC(18,8). Decimal, not float: a float rate reintroduces
the binary-rounding error that `core/money.py` exists to prevent.

Together with the existing `currency` column an order becomes
self-describing: amount, currency, source denomination and rate. It can be
audited, re-checked, and safely refused for re-conversion.

BACKFILL
--------
Existing rows are backfilled with `pricing_currency = currency` and
`fx_rate_used = 1.0`, which is EXACTLY TRUE for every order created before
this change: `MARKET_FX_RATES` was empty in production until 2026-09-30, so
`SettlementResolution.converted` was False and every historical order settled
1:1 in the price-book currency. This backfill is a statement of fact, not a
convenient default.

`fx_rate_used` is nullable with no server default going forward, so a future
code path that forgets to record the rate produces a visible NULL rather than
a plausible-looking 1.0. An honest gap beats a silent wrong number.

Revision: 0028_order_fx_lock
Revises:  0027_product_gender
"""
import sqlalchemy as sa
from alembic import op

revision: str = "0028_order_fx_lock"
down_revision: str = "0027_product_gender"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("pricing_currency", sa.String(10), nullable=True))
    op.add_column("orders", sa.Column("fx_rate_used", sa.Numeric(18, 8), nullable=True))

    # Backfill: true by construction for every pre-existing row (see docstring).
    op.execute(
        "UPDATE orders SET pricing_currency = currency, fx_rate_used = 1.0 "
        "WHERE pricing_currency IS NULL"
    )


def downgrade() -> None:
    op.drop_column("orders", "fx_rate_used")
    op.drop_column("orders", "pricing_currency")
