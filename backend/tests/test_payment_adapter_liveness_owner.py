"""Payment liveness has exactly ONE owner — and it is measured, never defaulted.

Why this file exists (2026-09-23, this cycle)
---------------------------------------------
`PaymentMethodOption.is_live` defaulting to `True` was the original defect: the
catalogue literal reached shoppers as "Tabby — Split in 4 … Sharia compliant,
is_live: true" on a deployment that held no Tabby key. PR #176 replaced the
literal with a measurement (`capability_service.payment_method_is_live`), gave
`PaymentMethodAvailability.is_live` no default, and added mutation gates for
both. That closed the *model*.

It did not close the *adapter*: `BasePaymentAdapter.__init__(name, is_live:
bool = False)` still accepted and stored a boolean called `is_live`. The class
has no subclasses in this repository and is never instantiated, so nothing
observable was wrong today — which is precisely why it is worth removing. It is
the class a developer writes a real PSP adapter by subclassing, and a second
field with that name, on that class, carrying a default, is a second source of
truth for the one fact this platform must never get wrong. A future
`if adapter.is_live:` reintroduces a liveness claim that no measurement made.

What is asserted
----------------
1. No class in `backend.app.providers.payment` declares an `is_live` attribute
   except `PaymentMethodAvailability`, the type produced by the measuring layer.
2. A concrete adapter subclass cannot expose a liveness field at all.
3. The structural property is expressed over the whole package, so a NEW module
   that adds one is caught rather than only the file that was fixed.

Mutation this kills: re-adding `is_live: bool = False` (or `True`) to
`BasePaymentAdapter.__init__` and assigning `self.is_live`.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil

import pytest

import backend.app.providers.payment as payment_pkg
from backend.app.providers.payment.base import BasePaymentAdapter
from backend.app.providers.payment.schemas import PaymentMethodAvailability

#: The only class allowed to carry liveness, because it is the only class that
#: is constructed by the measuring layer with a value it has just measured.
ALLOWED_LIVENESS_OWNER = {PaymentMethodAvailability}


def _payment_classes():
    """Every class defined by every module of the payment package."""
    for mod in pkgutil.iter_modules(payment_pkg.__path__):
        module = importlib.import_module(f"{payment_pkg.__name__}.{mod.name}")
        for name, obj in vars(module).items():
            if inspect.isclass(obj) and obj.__module__ == module.__name__:
                yield module.__name__, name, obj


def test_only_the_measured_model_may_declare_liveness():
    offenders = []
    for module_name, cls_name, cls in _payment_classes():
        if cls in ALLOWED_LIVENESS_OWNER:
            continue
        if hasattr(cls, "is_live") or "is_live" in vars(cls):
            offenders.append(f"{module_name}.{cls_name}")
    assert not offenders, (
        "these types declare `is_live` outside the measuring layer: "
        f"{offenders}. Liveness is a property of THIS deployment, produced by "
        "`capability_service.payment_method_is_live` and carried by "
        "`PaymentMethodAvailability` alone. A second field with that name — "
        "especially one with a default — can publish a claim no measurement "
        "made, which is how `bnpl_tabby` came to be served as live on a "
        "deployment with no Tabby credential."
    )


def test_adapter_constructor_takes_no_liveness_flag():
    params = inspect.signature(BasePaymentAdapter.__init__).parameters
    assert "is_live" not in params, (
        "BasePaymentAdapter.__init__ accepts `is_live`: a PSP adapter cannot "
        "know whether this deployment is live — that is decided by "
        "`PAYMENTS_LIVE`, an implemented adapter in `LIVE_PSP_ADAPTERS`, and the "
        f"provider credential. Signature was {params}"
    )


def test_a_concrete_adapter_cannot_expose_liveness():
    """The runtime shape, not just the signature: instantiate and look."""

    class _ProbeAdapter(BasePaymentAdapter):
        async def create_payment_intent(self, amount_minor, currency_code, customer_email,
                                        customer_phone=None, order_number=None, metadata=None):
            return {}

        async def verify_webhook_signature(self, payload_bytes, signature_header, secret):
            return False

        async def get_transaction_status(self, provider_tx_id):
            return {}

    adapter = _ProbeAdapter("probe")
    assert adapter.name == "probe"
    assert not hasattr(adapter, "is_live"), (
        "a constructed adapter exposes `.is_live` — liveness must be asked of "
        "`capability_service.payment_method_is_live(method_id)`, which consults "
        "the deployment's own configuration, never of an adapter instance"
    )
