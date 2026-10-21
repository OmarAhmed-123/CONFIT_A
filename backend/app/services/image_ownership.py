"""Brand ownership of image sources — the second control, not a replacement.

Two independent questions, two independent checks
-------------------------------------------------
``core/net_guard.assert_public_http_url`` answers *"is it safe for our server to
fetch this?"*. This module answers *"is this brand allowed to use it?"*.

Before this existed, the only ownership control was the deployment-wide
``CATALOG_IMPORT_ALLOW_OWN_IMAGES`` flag, which means "this server may fetch
first-party URLs" — not "THIS brand owns THAT host". With the flag on, any brand
could import a competitor's CDN photography and the platform would copy it into
the catalogue under the wrong brand. A flag cannot express ownership.

Neither check may stand in for the other:

* a hostname the brand has verified still goes through every net_guard check
  (a verified domain can point its DNS at 169.254.169.254);
* an address net_guard considers safe still has to belong to the brand
  (``images.attacker.example`` is a perfectly public host).

HOSTNAME POLICY — the part that has to be exactly right
-------------------------------------------------------
Matching a hostname to a verified domain is where a naive implementation becomes
a vulnerability, so the rules are stated and tested rather than implied:

1. **Normalize first.** Lowercase, strip a trailing dot, IDNA-encode to ASCII
   (so ``münchen.de`` and ``xn--mnchen-3ya.de`` are the same claim), and reject
   anything that is not a hostname (a scheme, a port, userinfo, a path).
2. **Exact match, or a subdomain.** ``cdn.example.com`` matches a verified
   ``example.com``. The reverse does not hold: verifying ``cdn.example.com``
   does not authorize ``example.com``.
3. **The label boundary is the dot.** ``evilexample.com`` is NOT a subdomain of
   ``example.com``, and ``example.com.attacker.net`` is not either. Both are
   the classic substring-matching failures, and both are pinned by tests.
4. **An IP literal is never an owned domain.** A brand cannot prove control of
   ``93.184.216.34`` by DNS TXT, and it must not be able to claim one. IPs go
   through net_guard only, and are refused as an ownership claim.
5. **Revoked means no.** ``revoked_at`` wins over ``verified_at``: revocation
   that a stale row could outvote would not be revocation.

What a brand is authorized to use, in full
------------------------------------------
* the platform's licensed stock hosts (``APPROVED_SOURCE_HOSTS``) — the
  platform holds that licence, so no per-brand claim is needed;
* any hostname it has verified itself, still subject to net_guard.

Anything else is refused with a specific, actionable reason.
"""
from __future__ import annotations

import ipaddress
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlsplit

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.models.user import BrandDomain

#: DNS TXT record prefix the brand publishes: ``confit-verify=<token>``.
TXT_PREFIX = "confit-verify="

#: A hostname label: 1-63 chars, alphanumeric and hyphen, no leading/trailing
#: hyphen. Applied to the ASCII (punycode) form.
_LABEL_RE = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")

#: Refusal reasons. Named constants so the API, the audit log and the tests all
#: agree on the vocabulary instead of comparing prose.
REASON_NO_SOURCE = "no_source"
REASON_MALFORMED_URL = "malformed_url"
REASON_IP_LITERAL = "ip_literal_not_ownable"
REASON_NOT_VERIFIED = "domain_not_verified"
REASON_OTHER_BRAND = "domain_owned_by_another_brand"
REASON_REVOKED = "domain_revoked"
REASON_EXPIRED = "domain_verification_expired"
REASON_STOCK_OK = "platform_stock_source"
REASON_VERIFIED = "verified_brand_domain"
DEFAULT_VERIFICATION_TTL_DAYS = 90


def verification_ttl_days() -> int:
    try:
        return max(1, int(getattr(settings, "BRAND_DOMAIN_VERIFICATION_TTL_DAYS", DEFAULT_VERIFICATION_TTL_DAYS)))
    except (TypeError, ValueError):
        return DEFAULT_VERIFICATION_TTL_DAYS


def domain_expires_at(record: BrandDomain, *, ttl_days: Optional[int] = None) -> Optional[datetime]:
    """Return UTC expiry instant for a verified domain, or None when unverified."""
    if getattr(record, "verified_at", None) is None:
        return None
    verified_at = record.verified_at
    if verified_at.tzinfo is None:
        verified_at = verified_at.replace(tzinfo=timezone.utc)
    days = ttl_days if ttl_days is not None else verification_ttl_days()
    return verified_at.astimezone(timezone.utc) + timedelta(days=days)


def is_domain_expired(
    record: BrandDomain,
    *,
    now: Optional[datetime] = None,
    ttl_days: Optional[int] = None,
) -> bool:
    exp = domain_expires_at(record, ttl_days=ttl_days)
    if exp is None:
        return False
    ref = now.astimezone(timezone.utc) if now is not None else datetime.now(timezone.utc)
    return ref >= exp


class OwnershipError(ValueError):
    """The brand is not authorized to import from this source."""

    def __init__(self, message: str, *, reason: str, hostname: str = ""):
        super().__init__(message)
        self.reason = reason
        self.hostname = hostname

    def to_dict(self) -> dict:
        return {"reason": self.reason, "hostname": self.hostname, "message": str(self)}


@dataclass(frozen=True)
class OwnershipDecision:
    """The verdict for one URL, with the provenance to report it honestly."""

    hostname: str
    allowed: bool
    reason: str
    #: ``stock`` (platform licence) or ``own`` (brand-verified domain).
    source_type: str
    matched_domain: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "hostname": self.hostname,
            "allowed": self.allowed,
            "reason": self.reason,
            "source_type": self.source_type,
            "matched_domain": self.matched_domain,
        }


# ---------------------------------------------------------------------------
# Hostname normalization and matching
# ---------------------------------------------------------------------------
def normalize_hostname(value: str) -> str:
    """Return the canonical ASCII hostname, or raise OwnershipError.

    Everything that matters for a security decision happens here: if a hostname
    can be normalized two ways, two different strings can be compared against
    one stored claim and the comparison is only as strict as its loosest input.
    """
    raw = (value or "").strip()
    if not raw:
        raise OwnershipError("No hostname was supplied", reason=REASON_MALFORMED_URL)

    # Refuse anything carrying structure a bare hostname cannot have. These
    # would otherwise survive `urlsplit` as a confusing hostname and be
    # compared against a verified claim.
    if any(ch in raw for ch in ("/", "\\", "@", "?", "#", " ")):
        raise OwnershipError(
            f"{raw!r} is not a bare hostname",
            reason=REASON_MALFORMED_URL, hostname=raw,
        )

    host = raw
    # Split off a port if present; only a numeric port is meaningful here.
    if host.startswith("["):  # IPv6 literal
        host = host.strip("[]")
    elif host.count(":") == 1:
        host, _, port = host.partition(":")
        if port and not port.isdigit():
            raise OwnershipError(
                f"{raw!r} has a non-numeric port",
                reason=REASON_MALFORMED_URL, hostname=raw,
            )

    host = host.rstrip(".").lower()
    if not host:
        raise OwnershipError("Empty hostname", reason=REASON_MALFORMED_URL)

    # IDNA: only the ASCII form is compared, so a Unicode claim and its
    # punycode equivalent cannot both exist as separate rows.
    if not host.isascii():
        try:
            host = host.encode("idna").decode("ascii")
        except (UnicodeError, ValueError) as exc:
            raise OwnershipError(
                f"{raw!r} is not a valid internationalized hostname",
                reason=REASON_MALFORMED_URL, hostname=raw,
            ) from exc

    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise OwnershipError(
            f"{raw!r} is an IP address; a brand cannot prove ownership of one by DNS",
            reason=REASON_IP_LITERAL, hostname=host,
        )

    if len(host) > 253:
        raise OwnershipError("Hostname is longer than 253 characters",
                             reason=REASON_MALFORMED_URL, hostname=host[:60])
    labels = host.split(".")
    if len(labels) < 2:
        # A single-label host is an internal service name on the deployment's own
        # network, never a brand's registrable domain.
        raise OwnershipError(
            f"{raw!r} is not a registrable domain",
            reason=REASON_MALFORMED_URL, hostname=host,
        )
    for label in labels:
        if not _LABEL_RE.match(label):
            raise OwnershipError(
                f"{raw!r} is not a valid hostname",
                reason=REASON_MALFORMED_URL, hostname=host,
            )
    return host


def hostname_matches(hostname: str, verified: str) -> bool:
    """True when ``hostname`` IS ``verified`` or a subdomain of it.

    The dot is the boundary. ``evilexample.com.endswith("example.com")`` is True,
    which is exactly why a suffix test alone is not used here.
    """
    host = hostname.rstrip(".").lower()
    domain = verified.rstrip(".").lower()
    if not host or not domain:
        return False
    return host == domain or host.endswith("." + domain)


def normalize_claim(value: str) -> str:
    """Normalize what a brand typed into the "verify this domain" field.

    Accepts either a bare hostname or a full URL, because a brand owner will
    paste ``https://shop.example.com/`` from their browser and being told that
    "is not a hostname" is a bad first experience for a security form. The
    RESULT is identical either way, so accepting the URL form widens the input
    without widening what can be claimed.
    """
    raw = (value or "").strip()
    if "://" in raw:
        return hostname_from_url(raw)
    return normalize_hostname(raw)


def hostname_from_url(url: str) -> str:
    """Extract and normalize the hostname of an http(s) URL."""
    parts = urlsplit((url or "").strip())
    if parts.scheme.lower() not in ("http", "https"):
        raise OwnershipError(
            f"Unsupported URL scheme {parts.scheme or '(none)'!r}; only http and https",
            reason=REASON_MALFORMED_URL,
        )
    return normalize_hostname(parts.hostname or "")


# ---------------------------------------------------------------------------
# The decision
# ---------------------------------------------------------------------------
class ImageOwnershipService:
    """Server-side authorization of an image source for one brand.

    Stateless apart from the database session; call it on every import path and
    every media-registration path rather than trusting a client-supplied
    `image_source` column.
    """

    def __init__(self, db):
        self.db = db

    # -- authorization -------------------------------------------------------
    def authorize_url(self, brand_id: int, url: str) -> OwnershipDecision:
        """Is `brand_id` allowed to import the image at `url`?

        Never raises for the ordinary refusal cases — returns a decision, so a
        caller can report every rejected row instead of aborting the file on
        the first. Raises only if the input cannot be parsed at all.
        """
        from backend.app.services.media_materialization_service import (
            MediaSourceNotApproved, provider_for_url,
        )

        if not url or not str(url).strip():
            return OwnershipDecision("", False, REASON_NO_SOURCE, "own")

        try:
            host = hostname_from_url(url)
        except OwnershipError as exc:
            return OwnershipDecision(getattr(exc, "hostname", ""), False,
                                     exc.reason, "own")

        # 1. The platform's licensed stock hosts. The licence is the PLATFORM's,
        #    so no per-brand claim is required — but this is an allowlist, not
        #    "any https URL", and `provider_for_url` is the same function the
        #    materialiser uses.
        try:
            provider_for_url(url)
        except MediaSourceNotApproved:
            pass
        else:
            return OwnershipDecision(host, True, REASON_STOCK_OK, "stock",
                                     matched_domain=host)

        # 2. A hostname this brand has verified.
        claimed = (
            self.db.query(BrandDomain)
            .filter(BrandDomain.hostname.isnot(None))
            .all()
        )
        matching = [c for c in claimed if hostname_matches(host, c.hostname)]

        if not matching:
            return OwnershipDecision(host, False, REASON_NOT_VERIFIED, "own")

        mine = [c for c in matching if c.brand_id == brand_id]
        if not mine:
            # Someone else's domain. Deliberately NOT distinguished further in
            # the brand-facing message (it would disclose another tenant's
            # domain); the audit log keeps the detail.
            logger.warning("image_ownership_cross_brand_attempt",
                           brand_id=brand_id, hostname=host)
            return OwnershipDecision(host, False, REASON_OTHER_BRAND, "own",
                                     matched_domain=matching[0].hostname)

        # Most specific claim first: if a brand verified both example.com and
        # cdn.example.com, the latter is the one that actually authorized this.
        mine.sort(key=lambda c: len(c.hostname), reverse=True)
        saw_expired = False
        for candidate in mine:
            if candidate.status == "revoked" or candidate.revoked_at is not None:
                continue
            if candidate.status == "verified":
                if is_domain_expired(candidate):
                    saw_expired = True
                    continue
                return OwnershipDecision(host, True, REASON_VERIFIED, "own",
                                         matched_domain=candidate.hostname)

        # The brand does hold a claim, but none of them is currently active & valid.
        primary = mine[0]
        if primary.status == "revoked" or primary.revoked_at is not None:
            reason = REASON_REVOKED
        elif saw_expired or (primary.status == "verified" and is_domain_expired(primary)):
            reason = REASON_EXPIRED
        else:
            reason = REASON_NOT_VERIFIED
        return OwnershipDecision(host, False, reason, "own",
                                 matched_domain=primary.hostname)

    def assert_url(self, brand_id: int, url: str) -> OwnershipDecision:
        """Authorize or raise — for callers that must not continue."""
        decision = self.authorize_url(brand_id, url)
        if not decision.allowed:
            raise OwnershipError(
                self.explain(decision), reason=decision.reason,
                hostname=decision.hostname,
            )
        return decision

    @staticmethod
    def explain(decision: OwnershipDecision) -> str:
        """Brand-facing sentence: what is wrong AND what to do about it."""
        if decision.reason == REASON_NOT_VERIFIED:
            return (
                f"{decision.hostname} is not a domain your brand has verified, so this "
                f"image cannot be imported. Add and verify the domain in your brand "
                f"settings, or use a licensed stock source on the allow-list."
            )
        if decision.reason == REASON_OTHER_BRAND:
            return (
                f"This image host is not available to your brand. If you believe it is "
                f"yours, verify the domain in your brand settings."
            )
        if decision.reason == REASON_REVOKED:
            return (
                f"Ownership of {decision.hostname} was revoked, so it no longer "
                f"authorizes imports. Re-verify the domain to import from it again."
            )
        if decision.reason == REASON_EXPIRED:
            return (
                f"Verification for {decision.hostname} has expired. Confirm the DNS TXT "
                f"record is still published and re-verify the domain to renew imports."
            )
        if decision.reason == REASON_IP_LITERAL:
            return (
                f"{decision.hostname} is an IP address. A brand cannot prove ownership "
                f"of an address; use a domain you control."
            )
        if decision.reason == REASON_MALFORMED_URL:
            return (
                f"The image URL is not a valid http(s) URL with a hostname. Use a full "
                f"public link to the image file."
            )
        return "This image source is not authorized for your brand."

    # -- domain registry -----------------------------------------------------
    def request_domain(self, brand_id: int, hostname: str) -> BrandDomain:
        """Create (or return) a pending claim and the TXT record to publish.

        Accepts a bare hostname or a full URL — see `normalize_claim`.
        """
        host = normalize_claim(hostname)
        existing = self.db.query(BrandDomain).filter(BrandDomain.hostname == host).first()
        if existing:
            if existing.brand_id != brand_id:
                # Same disclosure rule as above: do not confirm who owns it.
                raise OwnershipError(
                    "This domain is already registered to another brand.",
                    reason=REASON_OTHER_BRAND, hostname=host,
                )
            return existing

        record = BrandDomain(
            brand_id=brand_id, hostname=host, status="pending",
            token=secrets.token_urlsafe(24), method="dns_txt",
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        logger.info("brand_domain_claim_created", brand_id=brand_id, hostname=host)
        return record

    def verify_domain(self, brand_id: int, hostname: str, *, resolver=None) -> BrandDomain:
        """Check the DNS TXT claim and mark the domain verified if it holds.

        ``resolver`` is ``(hostname, token) -> bool``. It is injectable so the
        suite never depends on public DNS, and so an operator can run a
        verification with a specific resolver. Production uses ``dns_txt_resolver``.
        """
        host = normalize_hostname(hostname)
        record = (self.db.query(BrandDomain)
                  .filter(BrandDomain.hostname == host,
                          BrandDomain.brand_id == brand_id)
                  .first())
        if record is None:
            raise OwnershipError(
                "No pending claim exists for this domain; request it first.",
                reason=REASON_NOT_VERIFIED, hostname=host,
            )

        check = resolver or dns_txt_resolver
        now = datetime.now(timezone.utc)
        record.last_checked_at = now
        try:
            ok = bool(check(host, record.token))
        except Exception as exc:  # DNS failure is a failed check, not a crash
            record.status = "pending"
            record.last_error = f"{type(exc).__name__}: {exc}"[:300]
            self.db.commit()
            logger.warning("brand_domain_verify_failed", brand_id=brand_id,
                           hostname=host, error=record.last_error)
            return record

        if ok:
            record.status = "verified"
            record.verified_at = now
            record.revoked_at = None
            record.last_error = None
        else:
            record.status = "pending"
            record.verified_at = None
            record.last_error = f"no {TXT_PREFIX}{record.token} TXT record found"
        self.db.commit()
        self.db.refresh(record)
        logger.info("brand_domain_verify_result", brand_id=brand_id, hostname=host,
                    status=record.status)
        return record

    def revoke_domain(self, brand_id: int, hostname: str) -> BrandDomain:
        """Stop authorizing imports from a domain.

        Deliberately does NOT delete the row or the already-imported media:
        revocation is about what may be imported NEXT. Removing photographs that
        are already published would break live product pages, and is a separate,
        deliberate operation with its own consequences.
        """
        host = normalize_hostname(hostname)
        record = (self.db.query(BrandDomain)
                  .filter(BrandDomain.hostname == host,
                          BrandDomain.brand_id == brand_id)
                  .first())
        if record is None:
            raise OwnershipError("No domain claim exists for this brand.",
                                 reason=REASON_NOT_VERIFIED, hostname=host)
        record.status = "revoked"
        record.revoked_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(record)
        logger.info("brand_domain_revoked", brand_id=brand_id, hostname=host)
        return record

    def release_domain(self, brand_id: int, hostname: str) -> str:
        """Cancel and remove a brand's domain claim row completely.

        Used when a brand cancels a pending claim or transfers/releases a domain so
        another brand controller may subsequently register and verify a fresh claim.
        Existing materialized product images remain stored in CONFIT object storage.
        """
        host = normalize_hostname(hostname)
        record = (self.db.query(BrandDomain)
                  .filter(BrandDomain.hostname == host,
                          BrandDomain.brand_id == brand_id)
                  .first())
        if record is None:
            raise OwnershipError("No domain claim exists for this brand.",
                                 reason=REASON_NOT_VERIFIED, hostname=host)
        self.db.delete(record)
        self.db.commit()
        logger.info("brand_domain_released", brand_id=brand_id, hostname=host)
        return host


def dns_txt_resolver(hostname: str, token: str) -> bool:
    """Look for ``confit-verify=<token>`` in the hostname's TXT records.

    Uses `dnspython` when installed. A missing library is a failed verification,
    not a crash — and never a pass: an ownership check that cannot run must not
    authorize anything.
    """
    expected = f"{TXT_PREFIX}{token}"
    try:
        import dns.resolver  # type: ignore

        answers = dns.resolver.resolve(hostname, "TXT", lifetime=5)
    except ImportError:
        logger.error("dns_txt_resolver_unavailable",
                     note="dnspython is not installed; domain verification cannot run")
        return False
    except Exception as exc:  # NXDOMAIN, timeout, no TXT records
        logger.warning("dns_txt_lookup_failed", hostname=hostname,
                       error=f"{type(exc).__name__}: {exc}"[:200])
        return False

    for record in answers:
        try:
            text = b"".join(record.strings).decode("utf-8", "ignore")
        except AttributeError:  # older dnspython
            text = str(record).strip('"')
        if text.strip() == expected:
            return True
    return False
