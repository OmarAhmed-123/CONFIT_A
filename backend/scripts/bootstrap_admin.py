"""Promote an existing, verified account to platform admin — safely (G-12).

The audit that started this work could not test the admin surface at all, and
the reason was structural: ``seed_data.py`` creates ``admin@confit.io`` with a
publicly known password and *refuses to run in production* — correctly, because
a production database must never silently gain known demo credentials. But
nothing replaced it, so there was no sanctioned way to create a first admin.
The only options were "edit the database by hand" or "don't have an admin".

This script is the sanctioned path. What it deliberately does NOT do:

* **It never creates a user and never sets a password.** It promotes an account
  that already exists, is verified and is active. Creating an identity from a
  script means inventing credentials, and invented credentials are how demo
  logins end up in production.
* **It accepts no credential on the command line.** The authorisation token
  comes from the environment (``ADMIN_BOOTSTRAP_TOKEN``, at least 32
  characters), and a real change additionally requires ``--confirm``. The token
  is never printed, logged or audited.
* **It is idempotent.** Promoting an account that is already admin is a no-op
  that writes no second audit row, so a retried run cannot manufacture a
  history of escalations that did not happen.
* **It will not orphan the platform.** ``--revoke`` refuses to remove the last
  remaining admin.
* **Every promotion and revocation is audited** through the same
  ``UserRepository.log_audit`` write path the API uses, so the redaction
  controls added for G-06 apply here too.

Usage::

    # 1. an operator with deploy access sets a one-time token in the environment
    export ADMIN_BOOTSTRAP_TOKEN="$(openssl rand -hex 32)"

    # 2. preview, then apply
    python -m backend.scripts.bootstrap_admin --email someone@company.com --dry-run
    python -m backend.scripts.bootstrap_admin --email someone@company.com --confirm

    # 3. unset the token. It is single-use by procedure, not by magic.
    unset ADMIN_BOOTSTRAP_TOKEN

    # revoke (refuses if this is the last admin)
    python -m backend.scripts.bootstrap_admin --email someone@company.com --revoke --confirm

Exit codes: ``0`` success or safe no-op, ``1`` refused, ``2`` bad usage.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from typing import Optional, Tuple

from backend.app.core.config import settings
from backend.app.core.database import SessionLocal
from backend.app.models.user import User, UserRole
from backend.app.repositories.user_repository import UserRepository

ACTION_PROMOTE = "ADMIN_BOOTSTRAP_PROMOTE"
ACTION_REVOKE = "ADMIN_BOOTSTRAP_REVOKE"

#: Recorded as the actor when no human principal exists. Deliberately not a
#: user id: a script must not impersonate a person in the audit trail.
BOOTSTRAP_ACTOR = "system:bootstrap_admin"


class BootstrapRefused(RuntimeError):
    """Raised for every condition that must stop the script without a traceback."""


MIN_TOKEN_LENGTH = 32


def _authorise(confirm: bool) -> None:
    """Require a deliberate, out-of-band authorisation token.

    The token is not a substitute for having deploy access — anyone who can run
    this script already has it. Its job is to make the act *deliberate and
    reviewable*: an accidental run, a copy-pasted command, or the wrong pipeline
    invoking this all fail here instead of silently promoting someone.

    A short or absent token is refused outright, because a guessable token is
    worse than none: it would let the check pass while providing no evidence
    that anybody decided anything.
    """
    token = os.environ.get("ADMIN_BOOTSTRAP_TOKEN") or getattr(
        settings, "ADMIN_BOOTSTRAP_TOKEN", None
    )
    if not token:
        raise BootstrapRefused(
            "ADMIN_BOOTSTRAP_TOKEN is not set. Generate one "
            "(openssl rand -hex 32), export it, run this script, then unset it."
        )
    if len(str(token)) < MIN_TOKEN_LENGTH:
        raise BootstrapRefused(
            f"ADMIN_BOOTSTRAP_TOKEN is {len(str(token))} characters; at least "
            f"{MIN_TOKEN_LENGTH} are required. A guessable token is worse than "
            "none, because it lets the check pass while proving nothing."
        )
    if not confirm:
        raise BootstrapRefused(
            "pass --confirm to apply the change. Without it this script only "
            "reports what it would do."
        )


def _resolve_target(db, email: str) -> User:
    """Find the account to promote, refusing anything that is not ready."""
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if user is None:
        raise BootstrapRefused(
            f"no account exists for {email!r}. This script promotes an existing, "
            "verified account — it does not create identities. Provision the user "
            "through the normal signup/invite flow first."
        )
    if not user.is_active:
        raise BootstrapRefused(f"{email!r} is deactivated; reactivate the account first.")
    if not user.is_verified:
        raise BootstrapRefused(
            f"{email!r} has not verified its email address. Promoting an "
            "unverified mailbox would hand platform admin to whoever controls "
            "an address nobody has proven ownership of."
        )
    return user


def _count_admins(db) -> int:
    return db.query(User).filter(User.role == UserRole.ADMIN, User.is_active == True).count()  # noqa: E712


def _role_label(role) -> str:
    """The wire value of a role, for audit payloads."""
    value = getattr(role, "value", role)
    return str(value).lower()


def bootstrap_admin(
    email: str, revoke: bool = False, dry_run: bool = False, db=None
) -> Tuple[str, dict]:
    """Promote or demote one account. Returns (outcome, facts).

    Outcomes: ``promoted``, ``revoked``, ``already_admin``, ``not_admin``.
    The last two are safe no-ops that write no audit row.
    """
    owns_session = db is None
    session = db or SessionLocal()
    try:
        user = _resolve_target(session, email)
        # Recorded as the wire value ("admin"), never Python's enum repr
        # ("UserRole.ADMIN"). An auditor reading the trail should not have to
        # know how the code models a role to understand what changed.
        current = _role_label(user.role)
        target_role = UserRole.CONSUMER if revoke else UserRole.ADMIN
        label = _role_label(target_role)

        if user.role == target_role:
            return ("not_admin" if revoke else "already_admin"), {
                "email": user.email, "role": current, "changed": False
            }

        if revoke and _count_admins(session) <= 1:
            raise BootstrapRefused(
                f"{user.email} is the only active admin. Revoking would leave the "
                "platform with no administrator; promote a replacement first."
            )

        facts = {
            "email": user.email,
            "user_id": user.id,
            "before": {"role": current},
            "after": {"role": label},
            "admins_after": None,
        }
        if dry_run:
            facts["admins_after"] = (
                _count_admins(session) - 1 if revoke else _count_admins(session) + 1
            )
            return ("would_revoke" if revoke else "would_promote"), facts

        user.role = target_role
        session.flush()
        facts["admins_after"] = _count_admins(session)

        # Audited through the same write path the API uses, so G-06's redaction
        # applies. The token is never passed here.
        UserRepository(session).log_audit(
            action=ACTION_REVOKE if revoke else ACTION_PROMOTE,
            resource_type="User",
            resource_id=str(user.id),
            user_id=user.id,
            ip_address=None,
            details=f"bootstrap_admin by {BOOTSTRAP_ACTOR}; admins_after={facts['admins_after']}",
            before=facts["before"],
            after=facts["after"],
            request_id=f"bootstrap-{uuid.uuid4().hex[:12]}",
        )
        session.commit()
        return ("revoked" if revoke else "promoted"), facts
    except Exception:
        session.rollback()
        raise
    finally:
        if owns_session:
            session.close()


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--email", required=True, help="existing, verified account to change")
    parser.add_argument("--revoke", action="store_true", help="demote instead of promote")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, write nothing")
    parser.add_argument("--confirm", action="store_true",
                        help="required to apply a real change; absent means report-only")
    args = parser.parse_args(argv)

    if args.dry_run and args.confirm:
        print("REFUSED: --dry-run and --confirm are contradictory; pick one.", file=sys.stderr)
        return 2
    try:
        if not args.dry_run:
            # A dry run writes nothing, so it needs no authorisation. Anything
            # that touches the database does.
            _authorise(confirm=args.confirm)
        outcome, facts = bootstrap_admin(args.email, revoke=args.revoke, dry_run=args.dry_run)
    except BootstrapRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1

    verb = {
        "promoted": "promoted to platform admin",
        "revoked": "demoted from platform admin",
        "already_admin": "is already a platform admin (no change, no audit row written)",
        "not_admin": "is not a platform admin (no change, no audit row written)",
        "would_promote": "WOULD BE promoted to platform admin",
        "would_revoke": "WOULD BE demoted from platform admin",
    }[outcome]
    # The email is printed; the token never is.
    print(f"{facts['email']} {verb}; role {facts['before']['role']} -> {facts['after']['role']}"
          if "before" in facts else f"{facts['email']} {verb}")
    if facts.get("admins_after") is not None:
        print(f"active admins after this change: {facts['admins_after']}")
    if outcome in ("promoted", "revoked"):
        print("audited as " + (ACTION_REVOKE if args.revoke else ACTION_PROMOTE))
        if not args.revoke:
            print("next: unset ADMIN_BOOTSTRAP_TOKEN — it is single-use by procedure.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
