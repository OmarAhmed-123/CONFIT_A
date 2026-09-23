"""The return-authorisation reference is a BEARER capability — size it like one.

Defect (measured 2026-09-23, this cycle)
---------------------------------------
`GET /returns/labels/{ref}` is deliberately unauthenticated: a shopper who
requested a return must be able to download the authorisation document without
signing back in, and the route carries no `Depends(get_current_user)`. The only
thing protecting the document is the reference itself:

    ref = f"RA-{uuid.uuid4().hex[:10].upper()}"      # 10 hex characters

Ten hex characters is **40 bits** of entropy. The document that route returns
contains the order number, the return number and the return status. Two points
follow, and only the second is a defect:

  1. The generator is `uuid4`, a CSPRNG, so the value is unpredictable — this is
     not the `Math.random()` class of defect that the guest session token had.
  2. 40 bits is still below the size a bearer credential should be, and the
     guidance is consistent: OWASP's session-identifier guidance is 64+ bits of
     entropy (128 recommended), and the same reasoning applies to any value that
     *is* the credential. The regex on the route already accepts up to 16
     characters, so the fix is one constant, not a redesign.

This is recorded as a Weakness, not an exploit: reaching a valid reference would
require ~2^39 requests against a live service, which the rate limits make
impractical. The reason to fix it anyway is that capability entropy is a
property that should not depend on how much traffic an attacker is willing to
send.

What is asserted
----------------
* the random part of a generated reference is at least 16 hex characters
  (64 bits);
* generated references are distinct (no accidental constant/seed);
* the emitted reference still matches the shape `GET /returns/labels/{ref}`
  accepts, so the fix cannot silently break the download route — a capability
  nobody can redeem is not a fix.

Mutation this kills: reverting to `uuid.uuid4().hex[:10]`.
"""

from __future__ import annotations

import re

from backend.app.services.commerce_service import CommerceService

#: The shape the controller accepts (commerce_controller.download_return_label).
CONTROLLER_ACCEPTED = re.compile(r"RA-[A-Z0-9]{6,16}$")

#: 16 hex characters = 64 bits, the floor for a bearer capability.
MIN_RANDOM_CHARS = 16


def _make_ref() -> str:
    # `_generate_return_label` does not read the order (the reference is
    # generated from randomness alone), so no database row is needed to exercise
    # it — and this test deliberately avoids touching one.
    _, ref = CommerceService(db=None)._generate_return_label(order=None)  # type: ignore[arg-type]
    assert ref, "no reference was produced at all"
    return ref


def test_return_label_reference_carries_at_least_64_bits():
    ref = _make_ref()
    random_part = ref.split("-", 1)[1]
    assert len(random_part) >= MIN_RANDOM_CHARS, (
        f"return-label reference {ref!r} has {len(random_part)} characters "
        f"({len(random_part) * 4} bits) of randomness. This value is the ONLY "
        "protection on an unauthenticated endpoint that discloses the order "
        "number, so it must meet the 64-bit floor for a bearer capability."
    )


def test_return_label_reference_shape_still_redeemable():
    for _ in range(20):
        ref = _make_ref()
        assert CONTROLLER_ACCEPTED.match(ref), (
            f"{ref!r} would be rejected by `GET /returns/labels/{{ref}}` — the "
            "generator and the route's accepted shape must stay in agreement"
        )


def test_return_label_references_are_distinct():
    refs = {_make_ref() for _ in range(50)}
    assert len(refs) == 50, (
        "references are colliding, so two shoppers could be issued the same "
        "capability (and the repository lookup, which filters by this value, "
        "would return whichever row matched first)"
    )
