"""Provision a partner (brand) role for an existing, verified account — safely.

This closes the gap that ``bootstrap_admin.py`` left open. That script was
written because ``seed_data.py`` refuses to run in production — correctly, since
a production database must never silently gain ``admin@confit.io`` with a
publicly known password — and nothing had replaced it, so there was no
sanctioned way to create a first admin.

The identical gap still exists for the partner roles. ``POST /auth/register``
hard-codes ``CONSUMER`` (a deliberate P0 security invariant), and
``bootstrap_admin.py`` promotes only to ``ADMIN``. So on a production database
there is still no supported way to obtain a ``brand_owner``, ``brand_manager``
or ``brand_staff`` account: the only options are "edit the database by hand" or
"do not have a brand account". Editing tenant rows by hand is how a portal ends
up with a user whose ``role`` says ``brand_manager`` while ``brand_profiles``
has no row for them — which is exactly the "every request failed" failure mode
the partner portal is known for.

What this script deliberately does NOT do:

* **It never creates a user and never sets a password.** It provisions an
  account that already exists, is active and is verified. Creating an identity
  from a script means inventing credentials, and invented credentials are how
  demo logins end up in production.
* **It accepts no credential on the command line.** Authorisation comes from
  ``ROLE_BOOTSTRAP_TOKEN`` in the environment (at least 32 characters), and a
  real change additionally requires ``--confirm``. The token is never printed,
  logged or audited.
* **It provisions the tenant atomically.** A partner role is meaningless
  without a ``brand_profiles`` row, so the role change and the profile row are
  written in one transaction. There is no window in which the role says
  ``brand_manager`` and the tenant does not exist.
* **It is idempotent.** Provisioning an account that already holds the role —
  with its profile present — is a no-op that writes no second audit row, so a
  retried run cannot manufacture a history of escalations that did not happen.
* **It will not orphan the platform.** ``--revoke`` refuses to demote the last
  remaining admin.
* **It refuses to delete tenant data.** Demoting a partner role keeps the
  ``brand_profiles`` row and says so. Dropping a brand's profile is an
  operational task with real data-loss consequences, not a side effect of a
  role change.
* **Every change is audited** through the same ``UserRepository.log_audit``
  path the API uses, so the redaction controls apply here too.

Usage::

    # 1. an operator with deploy access sets a one-time token
    export ROLE_BOOTSTRAP_TOKEN="$(openssl rand -hex 32)"

    # 2. the account must already exist and be verified: sign up through the
    #    product first, then promote. Never the other way round.
    python -m backend.scripts.bootstrap_role \
        --email someone@brand.com --role brand_manager \
        --brand-name "Someone Studio" --dry-run

    python -m backend.scripts.bootstrap_role \
        --email someone@brand.com --role brand_manager \
        --brand-name "Someone Studio" --confirm

    # 3. unset the token. It is single-use by procedure, not by magic.
    unset ROLE_BOOTSTRAP_TOKEN

    # revoke (keeps the brand profile; refuses if this is the last admin)
    python -m backend.scripts.bootstrap_role --email someone@brand.com --revoke --confirm

Exit codes: ``0`` success or safe no-op, ``1`` refused, ``2`` bad usage.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import uuid
from typing import Optional, Tuple

from backend.app.core.config import settings
from backend.app.core.database import SessionLocal
from backend.app.models.user import BrandProfile, User, UserRole
from backend.app.repositories.user_repository import UserRepository

ACTION_PROVISION = "ROLE_BOOTSTRAP_PROVISION"
ACTION_REVOKE = "ROLE_BOOTSTRAP_REVOKE"

#: Recorded as the actor when no human principal exists. Deliberately not a
#: user id: a script must not impersonate a person in the audit trail.
BOOTSTRAP_ACTOR = "system:bootstrap_role"

#: Roles this script may grant. CONSUMER is the demotion target, not a choice.
PROVISIONABLE = ("brand_owner", "brand_manager", "brand_staff", "admin")

#: Roles whose portal surface is tenant-scoped: they need a brand_profiles row
#: before the B2B portal can serve them anything.
TENANT_ROLES = ("brand_owner", "brand_manager", "brand_staff")

MIN_TOKEN_LENGTH = 32


class BootstrapRefused(RuntimeError):
    """Raised for every condition that must stop the script without a traceback."""


def _authorise(confirm: bool) -> None:
    """Require a deliberate, out-of-band authorisation token.

    The token is not a substitute for having deploy access — anyone who can run
    this script already has it. Its job is to make the act *deliberate and
    reviewable*: an accidental run, a copy-pasted command, or the wrong pipeline
    invoking this all fail here instead of silently escalating someone.

    A short or absent token is refused outright, because a guessable token is
    worse than none: it would let the check pass while providing no evidence
    that anybody decided anything.
    """
    token = os.environ.get("ROLE_BOOTSTRAP_TOKEN") or getattr(
        settings, "ROLE_BOOTSTRAP_TOKEN", None
    )
    if not token:
        raise BootstrapRefused(
            "ROLE_BOOTSTRAP_TOKEN is not set. Generate one "
            "(openssl rand -hex 32), export it, run this script, then unset it."
        )
    if len(str(token)) < MIN_TOKEN_LENGTH:
        raise BootstrapRefused(
            f"ROLE_BOOTSTRAP_TOKEN is {len(str(token))} characters; at least "
            f"{MIN_TOKEN_LENGTH} are required. A guessable token is worse than "
            "none, because it lets the check pass while proving nothing."
        )
    if not confirm:
        raise BootstrapRefused(
            "pass --confirm to apply the change. Without it this script only "
            "reports what it would do."
        )


def _resolve_target(db, email: str) -> User:
    """Find the account to provision, refusing anything that is not ready."""
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if user is None:
        raise BootstrapRefused(
            f"no account exists for {email!r}. This script provisions an "
            "existing, verified account — it does not create identities. Sign "
            "up through the product (or invite the user) first, then run this."
        )
    if not user.is_active:
        raise BootstrapRefused(f"{email!r} is deactivated; reactivate the account first.")
    if not user.is_verified:
        raise BootstrapRefused(
            f"{email!r} has not verified its email address. Granting a "
            "partner role to an unverified mailbox would hand a brand's tenant "
            "to whoever controls an address nobody has proven ownership of."
        )
    return user


def _count_admins(db) -> int:
    return db.query(User).filter(User.role == UserRole.ADMIN, User.is_active == True).count()  # noqa: E712


def _role_label(role) -> str:
    """The wire value of a role, for audit payloads."""
    return str(getattr(role, "value", role)).lower()


def _slugify(name: str) -> str:
    """A readable, URL-safe slug. ASCII-only so URLs stay copy-pasteable."""
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug or "brand"


def _unique_slug(db, base: str) -> str:
    """Return `base`, or the first `base-2`, `base-3`… that is not taken.

    brand_profiles.slug is UNIQUE, so a re-run for a second brand with a
    similar name must not collide with the first.
    """
    candidate = base
    suffix = 1
    while db.query(BrandProfile).filter(BrandProfile.slug == candidate).first() is not None:
        suffix += 1
        candidate = f"{base}-{suffix}"
    return candidate


def _find_profile(db, user_id: int):
    return db.query(BrandProfile).filter(BrandProfile.user_id == user_id).first()


def bootstrap_role(
    email: str,
    role: str,
    brand_name: Optional[str] = None,
    revoke: bool = False,
    dry_run: bool = False,
    db=None,
) -> Tuple[str, dict]:
    """Provision or revoke one account's role. Returns (outcome, facts).

    Outcomes: ``provisioned``, ``revoked``, ``unchanged``, ``would_provision``,
    ``would_revoke``. ``unchanged`` is a safe no-op that writes no audit row.
    """
    owns_session = db is None
    session = db or SessionLocal()
    try:
        user = _resolve_target(session, email)
        current = _role_label(user.role)

        if revoke:
            target = UserRole.CONSUMER
            if user.role == target:
                return "unchanged", {"email": user.email, "role": current, "changed": False}
            if user.role == UserRole.ADMIN and _count_admins(session) <= 1:
                raise BootstrapRefused(
                    f"{user.email} is the only active admin. Revoking would "
                    "leave the platform with no administrator; promote a "
                    "replacement first."
                )
            existing = _find_profile(session, user.id)
            facts = {
                "email": user.email,
                "user_id": user.id,
                "before": {"role": current},
                "after": {"role": _role_label(target)},
                "profile": "retained" if existing else "none",
            }
            if dry_run:
                return "would_revoke", facts
            user.role = target
            session.flush()
            UserRepository(session).log_audit(
                action=ACTION_REVOKE,
                resource_type="User",
                resource_id=str(user.id),
                user_id=user.id,
                ip_address=None,
                details=f"bootstrap_role by {BOOTSTRAP_ACTOR}; profile={facts['profile']}",
                before=facts["before"],
                after=facts["after"],
                request_id=f"bootstrap-{uuid.uuid4().hex[:12]}",
                # P2 atomicity: the role change and its audit row must commit
                # together. log_audit() commits by default, which would persist
                # the audit separately from the mutation; commit=False hands the
                # decision back to this transaction.
                commit=False,
            )
            session.commit()
            return "revoked", facts

        # ---- provision -------------------------------------------------
        try:
            target = UserRole[role.upper()]
        except KeyError:
            raise BootstrapRefused(
                f"unknown role {role!r}; choose one of {', '.join(PROVISIONABLE)}."
            )
        if _role_label(target) not in PROVISIONABLE:
            raise BootstrapRefused(
                f"{role!r} is not provisionable; choose one of {', '.join(PROVISIONABLE)}."
            )

        needs_tenant = _role_label(target) in TENANT_ROLES
        existing = _find_profile(session, user.id)

        if user.role == target and (not needs_tenant or existing is not None):
            return "unchanged", {"email": user.email, "role": current, "changed": False}

        # A partner role without a tenant row is the exact broken state this
        # script exists to prevent. Refuse to create it, and say what to pass.
        profile_action = "unchanged"
        if needs_tenant and existing is None:
            if not brand_name or not brand_name.strip():
                raise BootstrapRefused(
                    f"{_role_label(target)} requires a brand profile, and "
                    f"{user.email} has none. Pass --brand-name \"Acme Studio\". "
                    "Refusing to grant a partner role without its tenant."
                )
            if (
                session.query(BrandProfile)
                .filter(BrandProfile.brand_name == brand_name.strip())
                .first()
                is not None
            ):
                raise BootstrapRefused(
                    f"a brand profile named {brand_name.strip()!r} already "
                    "exists. brand_name is UNIQUE; pick another name."
                )
            profile_action = "created"

        facts = {
            "email": user.email,
            "user_id": user.id,
            "before": {"role": current},
            "after": {"role": _role_label(target)},
            "profile": profile_action,
            "brand_name": brand_name.strip() if brand_name else None,
        }
        if dry_run:
            if profile_action == "created":
                facts["slug"] = _unique_slug(session, _slugify(brand_name))
            return "would_provision", facts

        if profile_action == "created":
            slug = _unique_slug(session, _slugify(brand_name))
            session.add(
                BrandProfile(
                    user_id=user.id,
                    brand_name=brand_name.strip(),
                    slug=slug,
                )
            )
            facts["slug"] = slug

        user.role = target
        session.flush()

        UserRepository(session).log_audit(
            action=ACTION_PROVISION,
            resource_type="User",
            resource_id=str(user.id),
            user_id=user.id,
            ip_address=None,
            details=(
                f"bootstrap_role by {BOOTSTRAP_ACTOR}; "
                f"profile={facts['profile']} slug={facts.get('slug')}"
            ),
            before=facts["before"],
            after=facts["after"],
            request_id=f"bootstrap-{uuid.uuid4().hex[:12]}",
            # P2 atomicity — see the revoke branch. The role change, the tenant
            # row and the audit row are one transaction: either all three
            # persist or none do.
            commit=False,
        )
        session.commit()
        return "provisioned", facts
    except Exception:
        session.rollback()
        raise
    finally:
        if owns_session:
            session.close()


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--email", required=True, help="existing, verified account to change")
    parser.add_argument(
        "--role",
        help="role to grant: " + ", ".join(PROVISIONABLE),
    )
    parser.add_argument(
        "--brand-name",
        help="required for brand_* roles when the account has no brand profile yet",
    )
    parser.add_argument("--revoke", action="store_true", help="demote to consumer instead")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, write nothing")
    parser.add_argument(
        "--confirm", action="store_true", help="required to apply a real change"
    )
    args = parser.parse_args(argv)

    if args.dry_run and args.confirm:
        print("REFUSED: --dry-run and --confirm are contradictory; pick one.", file=sys.stderr)
        return 2
    if not args.revoke and not args.role:
        print("REFUSED: --role is required (or pass --revoke).", file=sys.stderr)
        return 2
    if args.revoke and args.role:
        print("REFUSED: --revoke and --role are contradictory; pick one.", file=sys.stderr)
        return 2

    try:
        if not args.dry_run:
            # A dry run writes nothing, so it needs no authorisation. Anything
            # that touches the database does.
            _authorise(confirm=args.confirm)
        outcome, facts = bootstrap_role(
            args.email,
            role=args.role or "",
            brand_name=args.brand_name,
            revoke=args.revoke,
            dry_run=args.dry_run,
        )
    except BootstrapRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1

    verb = {
        "provisioned": "provisioned",
        "revoked": "demoted to consumer",
        "unchanged": "already holds this role (no change, no audit row written)",
        "would_provision": "WOULD BE provisioned",
        "would_revoke": "WOULD BE demoted to consumer",
    }[outcome]
    # The email is printed; the token never is.
    if outcome == "unchanged":
        print(f"{facts['email']} {verb}: {facts['role']}")
    else:
        print(f"{facts['email']} {verb}; role {facts['before']['role']} -> {facts['after']['role']}")
        print(f"brand profile: {facts['profile']}" + (f" (slug={facts['slug']})" if facts.get("slug") else ""))
    if outcome in ("provisioned", "revoked"):
        print("audited as " + (ACTION_REVOKE if args.revoke else ACTION_PROVISION))
        if not args.revoke:
            print("next: unset ROLE_BOOTSTRAP_TOKEN — it is single-use by procedure.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
