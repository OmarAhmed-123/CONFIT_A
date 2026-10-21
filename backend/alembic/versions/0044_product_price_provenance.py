"""0044 · products — keep the arithmetic behind a normalised price.

WHY: the importer can now accept a row priced in another currency (EGP) and
normalise it into the price book's denomination (USD) at import time. That
creates a new obligation the schema did not meet: once ``base_price`` has been
converted, the row no longer explains itself. "31.00" is not an auditable price
if nothing records that it used to be 1,614.79 EGP at 52.09, or when that rate
was published.

Without these columns a converted price is indistinguishable from a price the
brand typed in USD — so a support question ("why is this coat $31?") has no
answer in the database, and a later rate change cannot be shown NOT to have
touched it.

WHAT THIS ADDS (all nullable — an unconverted row keeps NULL, which is the
honest value for "this price was never converted"):

    price_source_currency   the brand's original currency, e.g. ``EGP``
    price_source_amount     the amount as supplied, NUMERIC(12,2)
    price_fx_rate           the published rate, PRICE_BOOK → SOURCE
                            (1 USD = 52.09 EGP). Same direction as
                            ``orders.fx_rate_used`` so the two are comparable.
    price_fx_source         ``live`` | ``configured``
    price_fx_as_of          the provider's publication timestamp

``compare_at_price`` is converted with the SAME rate as ``base_price`` and needs
no separate provenance: converting a strike-through at a different rate than the
price it sits beside would fabricate a discount percentage.

These are a SNAPSHOT of the import that wrote the row. They are deliberately not
recomputed: if the rate changes tomorrow, this product's price does not.

Additive and reversible. SQLite-safe (nullable columns, no table rebuild);
PostgreSQL-safe (no default, no rewrite — ADD COLUMN NULL is metadata-only).

Revision ID: 0044_product_price_provenance
Revises: 0043_import_job_payload
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0044_product_price_provenance"
down_revision: str = "0043_import_job_payload"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("price_source_currency", sa.String(length=3)),
    ("price_source_amount", sa.Numeric(12, 2)),
    ("price_fx_rate", sa.Numeric(18, 8)),
    ("price_fx_source", sa.String(length=32)),
    ("price_fx_as_of", sa.String(length=64)),
)


def upgrade() -> None:
    for name, type_ in _COLUMNS:
        op.add_column("products", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(_COLUMNS):
        op.drop_column("products", name)
