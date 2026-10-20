"""The ONE authority for what shipping costs.

Before this module existed the fee was computed twice, in two places that had
drifted apart, and the shopper paid the difference:

  * ``CommerceService._format_cart`` (the cart quote) had no express branch at
    all and could not be asked for one — ``GET /cart`` accepted no
    ``shipping_method`` — so every cart quoted the *standard* fee.
  * ``CommerceService.checkout`` had its own copy of the threshold test and did
    know about express.

Measured live on ``258a5fd``: a 245.00 cart quoted ``total=272.25``
(``shipping_amount=15.00``); checking out that same cart with
``shipping_method="express"`` charged ``total=292.25``
(``shipping_amount=35.00``). A 20.00 divergence between the number shown and
the number charged — CUS-01.

Both call sites now call :func:`compute_shipping_fee`. Parity is structural
rather than something a test has to remember to check, though
``backend/tests/test_cus01_shipping_parity.py`` checks it anyway.

Deliberately NOT here: tax, discounts, currency conversion. This function is
only about the delivery fee, and it always returns an exact ``Decimal`` in the
price book's currency.
"""

from __future__ import annotations

from decimal import Decimal

from backend.app.core.config import settings
from backend.app.core.money import money_max, to_decimal

#: Delivery methods the storefront can quote. ``bopis`` is a *fulfillment*
#: type, not a delivery method, and is handled separately below.
DELIVERY_METHODS = ("standard", "express")


def is_valid_delivery_method(shipping_method: str) -> bool:
    """True when ``shipping_method`` names a real delivery method."""
    return shipping_method in DELIVERY_METHODS


def compute_shipping_fee(
    subtotal: Decimal,
    discount: Decimal,
    fulfillment: str = "delivery",
    shipping_method: str = "standard",
) -> Decimal:
    """Return the delivery fee for a cart or an order.

    One function, one set of rules, so a cart quote and its order can never
    disagree about what delivery costs.

    Rules, in order:

    1. Boutique pickup (``bopis``) is collected in store and is always free,
       whatever delivery method was also named.
    2. A zero-value basket is not charged a delivery fee. The cart has always
       waived it here (that is how an empty cart renders 0.00) — checkout used
       to charge the standard fee instead, billing something the cart never
       quoted.
    3. At or above ``FREE_SHIPPING_THRESHOLD`` (measured on what is actually
       payable, i.e. subtotal minus discount) delivery is free for BOTH
       methods.
    4. Otherwise the configured fee for that method.

    Raises:
        ValueError: if ``shipping_method`` is not a real delivery method. Callers
            validate at the edge; failing loudly here is the backstop against a
            future caller silently pricing an unknown method as standard.
    """
    if not is_valid_delivery_method(shipping_method):
        raise ValueError(
            f"shipping_method must be one of {DELIVERY_METHODS}, got {shipping_method!r}"
        )

    if fulfillment == "bopis":
        return Decimal("0.00")

    subtotal_d = to_decimal(subtotal)
    payable = money_max(subtotal_d - to_decimal(discount), Decimal("0.00"))

    if subtotal_d == Decimal("0.00"):
        return Decimal("0.00")

    if payable >= to_decimal(settings.FREE_SHIPPING_THRESHOLD):
        return Decimal("0.00")

    fee = (
        settings.EXPRESS_SHIPPING_FEE
        if shipping_method == "express"
        else settings.STANDARD_SHIPPING_FEE
    )
    return to_decimal(fee)
