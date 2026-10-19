"""Phase 0.2 — server-side onboarding completion metadata (wizard-reappearing).

The bug these tests pin down
---------------------------
The first-run gate decided "does this shopper still need onboarding?" from
`UserOut.has_profile`, i.e. *does a `user_style_profiles` row exist*. A row is
created the instant the wizard saves anything, so:

  * a shopper who opened the wizard and saved one field,
  * or hit a split PATCH (`/me/budget`) on the profile page,

was `has_profile=True` — the gate said "onboarded, never prompt again" while
`onboarding_completed` was still False, and the wizard reappeared from the
other code path on the next fresh session. Two sources of truth, two answers.

`onboarding_completed` / `onboarding_completed_at` / `onboarding_version` are
now the single server-side answer. These tests assert the contract that makes
that answer trustworthy:

  1. No profile row            → not completed.
  2. Row exists, never finished → `has_profile` True AND `onboarding_completed`
     False (the exact state the old gate misread).
  3. Full wizard submission    → completed + timestamp + version.
  4. Re-submission             → timestamp moves forward, version recorded.
  5. Split PATCHes never complete onboarding (the fail-closed fix).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.main import app
from backend.app.models.profile import UserStyleProfile
from backend.tests.conftest import TestingSessionLocal

client = TestClient(app)


def _unique_email() -> str:
    return f"phase02_{uuid.uuid4().hex[:8]}@confit-testing.example.com"


def _register(email: str, password: str = "StrongPassw0rd!") -> dict:
    r = TestClient(app).post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Phase 0.2 User"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _token(email: str, password: str = "StrongPassw0rd!") -> str:
    r = TestClient(app).post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _me(token: str) -> dict:
    r = client.get("/api/v1/auth/me", headers=_auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def _user_id(email: str) -> int:
    db = TestingSessionLocal()
    try:
        from backend.app.models.user import User

        user = db.query(User).filter(User.email == email).one()
        return user.id
    finally:
        db.close()


def _profile_row(email: str) -> UserStyleProfile | None:
    db = TestingSessionLocal()
    try:
        return (
            db.query(UserStyleProfile)
            .filter(UserStyleProfile.user_id == _user_id(email))
            .one_or_none()
        )
    finally:
        db.close()


# =============================================================================
# 1. No profile at all → not completed, and nothing fabricated
# =============================================================================
def test_me_reports_not_completed_before_any_profile_exists():
    email = _unique_email()
    _register(email)
    token = _token(email)

    me = _me(token)
    assert me["has_profile"] is False
    assert me["onboarding_completed"] is False
    # Never invent a completion instant for a user who has submitted nothing.
    assert me["onboarding_completed_at"] is None
    assert me["onboarding_version"] is None


# =============================================================================
# 2. THE REGRESSION — a profile row is NOT evidence of completed onboarding
# =============================================================================
def test_profile_row_without_completion_is_not_reported_as_onboarded():
    """The state that made the wizard reappear: `has_profile=True` while the
    wizard was never finished. The API must say so explicitly instead of
    leaving the client to infer it from row existence."""
    email = _unique_email()
    _register(email)
    token = _token(email)

    # A single split PATCH creates the profile row (and must NOT complete
    # onboarding — see test 5). This is exactly what opening the profile page
    # and saving one field produces.
    r = client.patch(
        "/api/v1/me/budget",
        headers=_auth(token),
        json={"budget_monthly_min": 1000, "budget_monthly_max": 3000},
    )
    assert r.status_code == 200, r.text
    assert _profile_row(email) is not None, "precondition: the row must exist"

    me = _me(token)
    assert me["has_profile"] is True, "row exists — this is the misleading flag"
    assert me["onboarding_completed"] is False, (
        "a partial profile must NOT be reported as completed onboarding; "
        "the first-run gate keys off this flag"
    )
    assert me["onboarding_completed_at"] is None
    assert me["onboarding_version"] is None


# =============================================================================
# 3. A full wizard submission records completion, timestamp and version
# =============================================================================
def test_completing_onboarding_stamps_timestamp_and_version():
    email = _unique_email()
    _register(email)
    token = _token(email)

    before = datetime.now(timezone.utc) - timedelta(seconds=5)
    r = client.post(
        "/api/v1/profile/onboarding-quiz",
        headers=_auth(token),
        json={"style_archetypes": ["Minimalist"], "preferred_colors": ["Navy"]},
    )
    assert r.status_code == 200, r.text
    after_ = datetime.now(timezone.utc) + timedelta(seconds=5)

    me = _me(token)
    assert me["onboarding_completed"] is True
    assert me["onboarding_version"] == settings.ONBOARDING_WIZARD_VERSION
    assert me["onboarding_completed_at"] is not None

    stamped = datetime.fromisoformat(me["onboarding_completed_at"].replace("Z", "+00:00"))
    if stamped.tzinfo is None:  # SQLite hands back naive datetimes
        stamped = stamped.replace(tzinfo=timezone.utc)
    assert before <= stamped <= after_, f"completion instant {stamped} is not real 'now'"

    # And the persisted row agrees with the API — one source of truth.
    row = _profile_row(email)
    assert row is not None
    assert row.onboarding_completed is True
    assert row.onboarding_version == settings.ONBOARDING_WIZARD_VERSION
    assert row.onboarding_completed_at is not None


# =============================================================================
# 4. Re-submission moves the timestamp forward (re-onboarding after a bump)
# =============================================================================
def test_resubmitting_updates_completion_metadata():
    email = _unique_email()
    _register(email)
    token = _token(email)

    body = {"style_archetypes": ["Minimalist"]}
    assert client.post(
        "/api/v1/profile/onboarding-quiz", headers=_auth(token), json=body
    ).status_code == 200
    first = _me(token)["onboarding_completed_at"]
    assert first is not None

    # Rewinding the stored instant makes the "moved forward" assertion
    # deterministic without sleeping.
    db = TestingSessionLocal()
    try:
        row = (
            db.query(UserStyleProfile)
            .filter(UserStyleProfile.user_id == _user_id(email))
            .one()
        )
        row.onboarding_completed_at = datetime.now(timezone.utc) - timedelta(days=30)
        db.commit()
    finally:
        db.close()

    assert client.post(
        "/api/v1/profile/onboarding-quiz", headers=_auth(token), json=body
    ).status_code == 200

    second = _me(token)["onboarding_completed_at"]
    assert second is not None
    s1 = datetime.fromisoformat(first.replace("Z", "+00:00"))
    s2 = datetime.fromisoformat(second.replace("Z", "+00:00"))
    if s1.tzinfo is None:
        s1 = s1.replace(tzinfo=timezone.utc)
    if s2.tzinfo is None:
        s2 = s2.replace(tzinfo=timezone.utc)
    assert s2 > s1, "re-completion must refresh the timestamp, not keep a stale one"


# =============================================================================
# 5. Split PATCHes must never complete onboarding (fail-closed fix)
# =============================================================================
def test_split_patches_do_not_complete_onboarding():
    """`save_quiz_and_preferences` used to default `is_onboarding=True`, and
    every split PATCH called it without the keyword — so saving a budget field
    marked the entire wizard complete. Each split PATCH is exercised here."""
    email = _unique_email()
    _register(email)
    token = _token(email)

    patches = [
        ("/api/v1/me/style-profile", {"style_archetypes": ["Minimalist"]}),
        ("/api/v1/me/budget", {"budget_monthly_min": 500}),
        ("/api/v1/me/brands", {"preferred_brands": ["Zara"]}),
        ("/api/v1/me/size-fit", {"size_tops": "M"}),
    ]
    for path, payload in patches:
        r = client.patch(path, headers=_auth(token), json=payload)
        assert r.status_code == 200, f"{path}: {r.text}"

        me = _me(token)
        assert me["onboarding_completed"] is False, (
            f"{path} completed onboarding — a split PATCH must never do that"
        )
        assert me["onboarding_completed_at"] is None
        assert me["onboarding_version"] is None

    # ...while the full wizard payload still does.
    assert client.post(
        "/api/v1/profile/onboarding-quiz",
        headers=_auth(token),
        json={"style_archetypes": ["Minimalist"]},
    ).status_code == 200
    assert _me(token)["onboarding_completed"] is True
