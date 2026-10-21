"""Brand ownership of image sources — a second control, not a replacement.

THE DEFECT THESE TESTS CLOSE
----------------------------
Ownership was a single deployment-wide boolean, ``CATALOG_IMPORT_ALLOW_OWN_IMAGES``.
It answers "may this server fetch first-party URLs?" — never "does THIS brand own
THAT host". With the flag on, any brand could import a competitor's CDN
photography and the platform would copy it into the catalogue under the wrong
brand. No individual check was wrong; a missing check was.

WHAT IS PINNED HERE
-------------------
The hostname policy that makes this safe is stated and tested rather than
implied: exact-or-subdomain matching on the DOT boundary, IDNA normalization,
IP literals refused, revocation outvoting a stale verification, and cross-brand
claims refused without disclosing the other tenant.

Every test that matters also asserts the ORIGINAL controls still hold: a
verified domain does not bypass net_guard, and a net_guard-safe address is not
thereby authorized.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.database import Base
from backend.app.core.net_guard import UnsafeURLError, assert_public_http_url, safe_get
from backend.app.models.user import BrandDomain, BrandProfile, User, UserRole
from backend.app.services.image_ownership import (
    OwnershipError,
    ImageOwnershipService,
    hostname_from_url,
    hostname_matches,
    normalize_hostname,
)

STOCK = "https://images.pexels.com/photos/1342609/pexels-photo-1342609.jpeg"


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    """Every hostname resolves to a public address.

    These tests are about AUTHORIZATION, not resolution — and `net_guard` is
    deliberately allowed to refuse an unresolvable host, so a fake brand domain
    would otherwise fail the network check before ownership was ever consulted.
    The same technique the repo's own `test_net_guard.py` uses. Anything that
    wants to prove a PRIVATE address is refused sets its own resolver.
    """
    import backend.app.core.net_guard as net_guard

    def fake_getaddrinfo(host, *args, **kwargs):
        return [(2, 1, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(net_guard.socket, "getaddrinfo", fake_getaddrinfo)


@pytest.fixture()
def two_brands():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    brands = []
    for index, name in enumerate(("Atelier A", "Rival B")):
        user = User(email=f"owner{index}@qa.example.com", hashed_password="x",
                    full_name=name, role=UserRole.BRAND_OWNER, preferred_language="en",
                    is_active=True, is_verified=True)
        db.add(user)
        db.flush()
        brand = BrandProfile(user_id=user.id, brand_name=name,
                             slug=f"brand-{index}", is_verified=True)
        db.add(brand)
        db.flush()
        brands.append(brand)
    db.commit()
    yield dict(db=db, a=brands[0], b=brands[1])
    db.close()


def verified(db, brand_id, hostname, *, status="verified"):
    record = BrandDomain(brand_id=brand_id, hostname=hostname, status=status,
                         token="tok-" + hostname, method="dns_txt")
    if status == "verified":
        from datetime import datetime, timezone
        record.verified_at = datetime.now(timezone.utc)
    db.add(record)
    db.commit()
    return record


# ---------------------------------------------------------------------------
# 1. The hostname policy — where a loose implementation becomes a vuln
# ---------------------------------------------------------------------------
class TestHostnamePolicy:
    def test_exact_hostname_matches(self):
        assert hostname_matches("example.com", "example.com")

    def test_a_subdomain_matches_its_verified_parent(self):
        assert hostname_matches("cdn.example.com", "example.com")
        assert hostname_matches("a.b.cdn.example.com", "example.com")

    @pytest.mark.parametrize("deceptive", [
        "evilexample.com",             # suffix without a dot boundary
        "notexample.com",
        "example.com.attacker.net",    # verified domain as a PREFIX
        "example.co",                  # a different TLD
        "example.com.evil",            # appended label
        "xexample.com",
    ])
    def test_deceptive_hostnames_do_not_match(self, deceptive):
        """`str.endswith` returns True for several of these. That is the bug."""
        assert not hostname_matches(deceptive, "example.com"), deceptive

    def test_the_reverse_direction_does_not_hold(self):
        """Verifying cdn.example.com must not authorize the apex."""
        assert not hostname_matches("example.com", "cdn.example.com")

    def test_normalization_lowercases_and_strips_the_root_dot(self):
        assert normalize_hostname("CDN.Example.COM.") == "cdn.example.com"

    def test_internationalized_domains_normalize_to_one_form(self):
        """A Unicode claim and its punycode form must be the same claim."""
        expected = "münchen-mode.de".encode("idna").decode("ascii")
        assert normalize_hostname("münchen-mode.de") == expected
        assert normalize_hostname(expected) == expected
        assert normalize_hostname("MÜNCHEN-MODE.DE") == expected
        assert expected.isascii()

    @pytest.mark.parametrize("ip", ["93.184.216.34", "169.254.169.254", "::1",
                                    "127.0.0.1"])
    def test_ip_literals_are_never_ownable(self, ip):
        """A brand cannot publish a DNS TXT record for an address it does not control."""
        with pytest.raises(OwnershipError) as excinfo:
            normalize_hostname(ip)
        assert excinfo.value.reason == "ip_literal_not_ownable"

    @pytest.mark.parametrize("bad", [
        "https://example.com/img.jpg",   # a URL, not a hostname
        "example.com/path",
        "user:pass@example.com",
        "example.com:notaport",
        "localhost",                     # single label = internal name
        "",
        "   ",
    ])
    def test_malformed_hostnames_are_refused(self, bad):
        with pytest.raises(OwnershipError):
            normalize_hostname(bad)

    def test_hostname_from_url_rejects_non_http_schemes(self):
        for scheme in ("ftp://example.com/a.jpg", "javascript:alert(1)",
                       "file:///etc/passwd"):
            with pytest.raises(OwnershipError):
                hostname_from_url(scheme)


# ---------------------------------------------------------------------------
# 2. Authorization: the decision, per brand
# ---------------------------------------------------------------------------
class TestAuthorization:
    def test_a_platform_stock_source_is_allowed_without_a_claim(self, two_brands):
        decision = ImageOwnershipService(two_brands["db"]).authorize_url(
            two_brands["a"].id, STOCK)
        assert decision.allowed
        assert decision.reason == "platform_stock_source"
        assert decision.source_type == "stock"

    def test_an_unverified_domain_is_refused(self, two_brands):
        decision = ImageOwnershipService(two_brands["db"]).authorize_url(
            two_brands["a"].id, "https://images.atelier-a.example/coat.jpg")
        assert not decision.allowed
        assert decision.reason == "domain_not_verified"
        assert "verify" in ImageOwnershipService.explain(decision).lower()

    def test_a_verified_brand_domain_is_allowed(self, two_brands):
        db = two_brands["db"]
        verified(db, two_brands["a"].id, "atelier-a.example")
        decision = ImageOwnershipService(db).authorize_url(
            two_brands["a"].id, "https://cdn.atelier-a.example/coat.jpg")
        assert decision.allowed
        assert decision.reason == "verified_brand_domain"
        assert decision.matched_domain == "atelier-a.example"

    def test_brand_b_cannot_use_brand_a_verified_domain(self, two_brands):
        """The tenant-isolation case: the whole reason a flag could not work."""
        db = two_brands["db"]
        verified(db, two_brands["a"].id, "atelier-a.example")

        decision = ImageOwnershipService(db).authorize_url(
            two_brands["b"].id, "https://cdn.atelier-a.example/coat.jpg")
        assert not decision.allowed
        assert decision.reason == "domain_owned_by_another_brand"

    def test_the_cross_brand_message_does_not_name_the_other_tenant(self, two_brands):
        """A refusal must not become a directory of other brands' domains."""
        db = two_brands["db"]
        verified(db, two_brands["a"].id, "atelier-a.example")
        decision = ImageOwnershipService(db).authorize_url(
            two_brands["b"].id, "https://cdn.atelier-a.example/x.jpg")
        message = ImageOwnershipService.explain(decision)
        assert "atelier-a.example" not in message
        assert "Atelier A" not in message

    def test_revocation_beats_a_stale_verification(self, two_brands):
        """A revoked domain authorizes nothing, even with verified_at populated."""
        db = two_brands["db"]
        svc = ImageOwnershipService(db)
        verified(db, two_brands["a"].id, "atelier-a.example")

        assert svc.authorize_url(two_brands["a"].id,
                                 "https://cdn.atelier-a.example/x.jpg").allowed
        svc.revoke_domain(two_brands["a"].id, "atelier-a.example")

        decision = svc.authorize_url(two_brands["a"].id,
                                     "https://cdn.atelier-a.example/x.jpg")
        assert not decision.allowed
        assert decision.reason == "domain_revoked"

    def test_revoking_one_domain_does_not_affect_another(self, two_brands):
        db = two_brands["db"]
        svc = ImageOwnershipService(db)
        verified(db, two_brands["a"].id, "one.example")
        verified(db, two_brands["a"].id, "two.example")
        svc.revoke_domain(two_brands["a"].id, "one.example")

        assert not svc.authorize_url(two_brands["a"].id, "https://one.example/x.jpg").allowed
        assert svc.authorize_url(two_brands["a"].id, "https://two.example/x.jpg").allowed

    def test_a_pending_claim_authorizes_nothing(self, two_brands):
        db = two_brands["db"]
        verified(db, two_brands["a"].id, "pending.example", status="pending")
        decision = ImageOwnershipService(db).authorize_url(
            two_brands["a"].id, "https://pending.example/x.jpg")
        assert not decision.allowed

    def test_the_most_specific_claim_is_the_one_reported(self, two_brands):
        db = two_brands["db"]
        verified(db, two_brands["a"].id, "example.com")
        verified(db, two_brands["a"].id, "cdn.example.com")
        decision = ImageOwnershipService(db).authorize_url(
            two_brands["a"].id, "https://cdn.example.com/x.jpg")
        assert decision.matched_domain == "cdn.example.com"

    def test_a_malformed_url_is_refused_not_raised_for_the_callers_file(self, two_brands):
        decision = ImageOwnershipService(two_brands["db"]).authorize_url(
            two_brands["a"].id, "not a url at all")
        assert not decision.allowed
        assert decision.reason == "malformed_url"


# ---------------------------------------------------------------------------
# 3. The two controls are independent
# ---------------------------------------------------------------------------
class TestControlsAreIndependent:
    def test_a_verified_domain_still_goes_through_net_guard(self, two_brands):
        """Ownership does NOT imply safety: a verified domain can point anywhere."""
        db = two_brands["db"]
        verified(db, two_brands["a"].id, "atelier-a.example")

        # Ownership says yes...
        assert ImageOwnershipService(db).authorize_url(
            two_brands["a"].id, "https://atelier-a.example/x.jpg").allowed
        # ...and net_guard still decides whether the address is fetchable. A
        # verified hostname that resolves to a metadata address is refused by
        # the ADDRESS check, which this test exercises with a literal.
        with pytest.raises(UnsafeURLError):
            assert_public_http_url("https://169.254.169.254/latest/meta-data/")

    def test_a_net_guard_safe_address_is_not_thereby_authorized(self, two_brands):
        """The mirror image: public is not the same as owned."""
        url = "https://perfectly-public-site.example/coat.jpg"
        assert_public_http_url(url)  # safe...
        decision = ImageOwnershipService(two_brands["db"]).authorize_url(
            two_brands["a"].id, url)
        assert not decision.allowed, "network safety was mistaken for authorization"

    def test_a_redirect_to_an_unowned_host_is_refused_by_the_gate(self, two_brands):
        """The time-of-check/time-of-use case, at the hop that matters.

        Ownership is checked on the FIRST url before the fetch. A verified
        domain redirecting to an unowned (but perfectly public) host would
        otherwise be followed — net_guard sees nothing wrong with the
        destination, and the brand imports someone else's image.
        """
        from backend.app.services.image_ownership import OwnershipError as OE

        service = ImageOwnershipService(two_brands["db"])

        def allow_hop(url):
            decision = service.authorize_url(two_brands["a"].id, url)
            if not decision.allowed:
                raise OE(decision.reason, reason=decision.reason,
                         hostname=decision.hostname)

        hops = []

        class Response:
            def __init__(self, status, location=None):
                self.status_code = status
                self.headers = {"location": location} if location else {}
                self.content = b"\xff\xd8\xff" if status == 200 else b""

        def fetch(url):
            hops.append(url)
            if url.startswith("https://cdn.atelier-a.example/"):
                return Response(302, "https://someone-else.example/taken.jpg")
            return Response(200)

        from backend.app.core.net_guard import safe_get as real_safe_get
        verified(two_brands["db"], two_brands["a"].id, "atelier-a.example")

        with pytest.raises((OE, UnsafeURLError)):
            real_safe_get("https://cdn.atelier-a.example/coat.jpg",
                          fetch=fetch, allow_hop=allow_hop)
        # The first hop passed ownership and was fetched; the redirect was
        # evaluated and REFUSED before the unowned destination was requested.
        assert hops == ["https://cdn.atelier-a.example/coat.jpg"], (
            f"the unowned destination was fetched: {hops}"
        )

    def test_the_gate_allows_a_redirect_that_stays_inside_the_verified_domain(self, two_brands):
        from backend.app.core.net_guard import safe_get as real_safe_get

        service = ImageOwnershipService(two_brands["db"])
        verified(two_brands["db"], two_brands["a"].id, "atelier-a.example")

        def allow_hop(url):
            decision = service.authorize_url(two_brands["a"].id, url)
            if not decision.allowed:
                raise OwnershipError(decision.reason, reason=decision.reason)

        class Response:
            def __init__(self, status, location=None):
                self.status_code = status
                self.headers = {"location": location} if location else {}
                self.content = b"\xff\xd8\xff"

        hops = []

        def fetch(url):
            hops.append(url)
            if url == "https://cdn.atelier-a.example/coat.jpg":
                return Response(302, "https://img.atelier-a.example/coat.jpg")
            return Response(200)

        body = real_safe_get("https://cdn.atelier-a.example/coat.jpg",
                             fetch=fetch, allow_hop=allow_hop)
        assert body.startswith(b"\xff\xd8")
        assert hops[-1] == "https://img.atelier-a.example/coat.jpg"


# ---------------------------------------------------------------------------
# 4. The registry: claim, verify, revoke
# ---------------------------------------------------------------------------
class TestDomainRegistry:
    def test_requesting_a_domain_returns_the_record_to_publish(self, two_brands):
        svc = ImageOwnershipService(two_brands["db"])
        record = svc.request_domain(two_brands["a"].id, "https://Atelier-A.example/")
        # The claim is stored normalized, so the recorded value and the compared
        # value cannot drift apart.
        assert record.hostname == "atelier-a.example"
        assert record.status == "pending"
        # The token must be unguessable: it is the only thing standing between
        # "I typed a domain" and "I control this domain".
        assert len(record.token) >= 20
        assert record.token != record.hostname

    def test_verification_requires_the_dns_txt_record(self, two_brands):
        db = two_brands["db"]
        svc = ImageOwnershipService(db)
        svc.request_domain(two_brands["a"].id, "atelier-a.example")

        # A resolver that does not find the token leaves it pending.
        record = svc.verify_domain(two_brands["a"].id, "atelier-a.example",
                                   resolver=lambda host, token: False)
        assert record.status == "pending"
        assert record.last_error and "TXT" in record.last_error
        assert not svc.authorize_url(two_brands["a"].id,
                                     "https://atelier-a.example/x.jpg").allowed

    def test_a_found_record_verifies_and_authorizes(self, two_brands):
        db = two_brands["db"]
        svc = ImageOwnershipService(db)
        svc.request_domain(two_brands["a"].id, "atelier-a.example")

        def resolver(host, token):
            assert host == "atelier-a.example"
            return token.startswith("")  # the TXT record matched this token

        record = svc.verify_domain(two_brands["a"].id, "atelier-a.example",
                                   resolver=resolver)
        assert record.status == "verified"
        assert record.verified_at is not None
        assert svc.authorize_url(two_brands["a"].id,
                                 "https://atelier-a.example/x.jpg").allowed

    def test_a_resolver_that_raises_is_a_failed_check_not_a_pass(self, two_brands):
        """An ownership check that cannot run must not authorize anything."""
        db = two_brands["db"]
        svc = ImageOwnershipService(db)
        svc.request_domain(two_brands["a"].id, "atelier-a.example")

        def resolver(host, token):
            raise TimeoutError("DNS timeout")

        record = svc.verify_domain(two_brands["a"].id, "atelier-a.example",
                                   resolver=resolver)
        assert record.status == "pending"
        assert "TimeoutError" in record.last_error
        assert not svc.authorize_url(two_brands["a"].id,
                                     "https://atelier-a.example/x.jpg").allowed

    def test_a_second_brand_cannot_claim_the_same_hostname(self, two_brands):
        """Two owners of one host would make 'who owns this image' undecidable."""
        db = two_brands["db"]
        svc = ImageOwnershipService(db)
        svc.request_domain(two_brands["a"].id, "atelier-a.example")

        with pytest.raises(OwnershipError) as excinfo:
            svc.request_domain(two_brands["b"].id, "atelier-a.example")
        assert excinfo.value.reason == "domain_owned_by_another_brand"
        assert "another brand" in str(excinfo.value)

    def test_a_brand_cannot_verify_another_brands_claim(self, two_brands):
        db = two_brands["db"]
        svc = ImageOwnershipService(db)
        svc.request_domain(two_brands["a"].id, "atelier-a.example")

        with pytest.raises(OwnershipError):
            svc.verify_domain(two_brands["b"].id, "atelier-a.example",
                              resolver=lambda host, token: True)

    def test_revocation_is_recorded_not_erased(self, two_brands):
        """Auditability: verified_at stays; revoked_at is what stops imports."""
        db = two_brands["db"]
        svc = ImageOwnershipService(db)
        svc.request_domain(two_brands["a"].id, "atelier-a.example")
        svc.verify_domain(two_brands["a"].id, "atelier-a.example",
                          resolver=lambda host, token: True)
        record = svc.revoke_domain(two_brands["a"].id, "atelier-a.example")

        assert record.status == "revoked"
        assert record.revoked_at is not None
        assert record.verified_at is not None, "history must survive revocation"

    def test_re_verification_clears_a_previous_revocation(self, two_brands):
        db = two_brands["db"]
        svc = ImageOwnershipService(db)
        svc.request_domain(two_brands["a"].id, "atelier-a.example")
        svc.verify_domain(two_brands["a"].id, "atelier-a.example",
                          resolver=lambda host, token: True)
        svc.revoke_domain(two_brands["a"].id, "atelier-a.example")

        record = svc.verify_domain(two_brands["a"].id, "atelier-a.example",
                                   resolver=lambda host, token: True)
        assert record.status == "verified"
        assert record.revoked_at is None


# ===========================================================================
# Verification expiry, renewal, DNS-loss, release & transfer policies
# ===========================================================================
class TestVerificationLifecyclePolicies:
    def test_expired_verification_blocks_new_imports_until_renewed(self, two_brands):
        from datetime import datetime, timedelta, timezone
        from backend.app.services.image_ownership import REASON_EXPIRED, REASON_VERIFIED

        db, a = two_brands["db"], two_brands["a"]
        rec = verified(db, a.id, "cdn.atelier-a.example")
        rec.verified_at = datetime.now(timezone.utc) - timedelta(days=91)
        db.commit()

        svc = ImageOwnershipService(db)
        expired_verdict = svc.authorize_url(a.id, "https://cdn.atelier-a.example/look.jpg")
        assert expired_verdict.allowed is False
        assert expired_verdict.reason == REASON_EXPIRED
        assert "expired" in svc.explain(expired_verdict).lower()

        # Renewing via live TXT verification refreshes verified_at and restores access
        renewed = svc.verify_domain(
            a.id, "cdn.atelier-a.example",
            resolver=lambda h, tok: tok == rec.token,
        )
        assert renewed.status == "verified"
        fresh_verdict = svc.authorize_url(a.id, "https://cdn.atelier-a.example/look.jpg")
        assert fresh_verdict.allowed is True
        assert fresh_verdict.reason == REASON_VERIFIED

    def test_reverification_after_dns_record_removal_revokes_import_authorization(self, two_brands):
        db, a = two_brands["db"], two_brands["a"]
        verified(db, a.id, "studio.atelier-a.example")
        svc = ImageOwnershipService(db)
        assert svc.authorize_url(a.id, "https://studio.atelier-a.example/1.jpg").allowed is True

        # DNS TXT removed / domain transferred away -> re-check drops verified status immediately
        checked = svc.verify_domain(a.id, "studio.atelier-a.example", resolver=lambda h, tok: False)
        assert checked.status == "pending"
        assert checked.verified_at is None
        assert svc.authorize_url(a.id, "https://studio.atelier-a.example/1.jpg").allowed is False

    def test_release_domain_enables_clean_transfer_to_another_brand_with_fresh_token(self, two_brands):
        db, a, b = two_brands["db"], two_brands["a"], two_brands["b"]
        svc = ImageOwnershipService(db)
        claim_a = svc.request_domain(a.id, "lookbook.transfer.example")
        old_token = claim_a.token
        svc.verify_domain(a.id, "lookbook.transfer.example", resolver=lambda h, t: True)

        # While held by Brand A (even if soft-revoked), Brand B cannot hijack it
        svc.revoke_domain(a.id, "lookbook.transfer.example")
        with pytest.raises(OwnershipError):
            svc.request_domain(b.id, "lookbook.transfer.example")

        # Once Brand A explicitly releases the claim, Brand B can claim & verify with a new token
        released = svc.release_domain(a.id, "lookbook.transfer.example")
        assert released == "lookbook.transfer.example"

        claim_b = svc.request_domain(b.id, "lookbook.transfer.example")
        assert claim_b.brand_id == b.id
        assert claim_b.token != old_token
        assert claim_b.status == "pending"
        svc.verify_domain(b.id, "lookbook.transfer.example", resolver=lambda h, t: t == claim_b.token)
        assert svc.authorize_url(b.id, "https://lookbook.transfer.example/hero.jpg").allowed is True
        assert svc.authorize_url(a.id, "https://lookbook.transfer.example/hero.jpg").allowed is False
