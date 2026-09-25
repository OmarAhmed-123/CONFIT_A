"""Round-3 concurrency proof — MFA single-use guarantees on REAL PostgreSQL.

Finding R3-1: the TOTP replay guard, recovery-code consumption and enrollment
confirmation were check-then-act sequences with no atomicity. A sequential
test (request 1 passes, request 2 fails) proves nothing about the production
topology — Vercel serverless runs many instances against one shared Postgres,
so two requests carrying the SAME code can interleave between the check and
the write. This suite executes genuinely concurrent transactions (separate
connections, barrier-synchronized threads) against a real PostgreSQL and
asserts the single-use invariants hold:

  1. N concurrent logins with the same TOTP code  -> exactly 1 session.
  2. N concurrent uses of the same recovery code  -> exactly 1 success.
  3. N concurrent enrollment confirms             -> exactly 1 recovery-code set.

Runs ONLY when CONFIT_CONCURRENCY_PG_URL points at a throwaway PostgreSQL
database (it creates/drops the schema). Skipped otherwise — SQLite cannot
model multi-connection interleaving (writers are globally serialized), which
is precisely why this file exists.

    CONFIT_CONCURRENCY_PG_URL=postgresql://... pytest backend/tests/test_mfa_concurrency_postgres.py
"""
import os
import threading
import time

import pyotp
import pytest

PG_URL = os.environ.get("CONFIT_CONCURRENCY_PG_URL", "")

pytestmark = pytest.mark.skipif(
    not PG_URL.startswith(("postgresql://", "postgres://", "postgresql+")),
    reason="CONFIT_CONCURRENCY_PG_URL not set to a PostgreSQL DSN (throwaway DB required)",
)

_CONCURRENCY = 6  # parallel attempts per invariant


@pytest.fixture(scope="module")
def pg():
    """Engine + fresh schema on the throwaway PostgreSQL database."""
    from sqlalchemy.orm import sessionmaker
    from backend.app.core.database import Base
    from backend.app.core.postgres_url import normalise_postgres_url
    from sqlalchemy import create_engine

    url, connect_args = normalise_postgres_url(PG_URL)
    engine = create_engine(url, connect_args=connect_args, pool_size=_CONCURRENCY + 4, max_overflow=4)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield engine, sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _make_mfa_user(SessionLocal, email: str):
    """Create a user enrolled in MFA; return (user_id, totp_secret, recovery_codes)."""
    from backend.app.services.auth_service import AuthService

    db = SessionLocal()
    try:
        svc = AuthService(db)
        out = svc.register(email=email, password="StrongPassw0rd!", full_name="Concurrency Probe")
        user = svc.user_repo.get_by_email(email)
        setup = svc.setup_mfa(user)
        secret = setup["secret"]
        totp = pyotp.TOTP(secret)
        enabled = svc.verify_mfa_setup(user, totp.now())
        return user.id, secret, enabled["backup_codes"]
    finally:
        db.close()


def _wait_next_step(secret: str) -> str:
    """A TOTP code for a FRESH time step (the enrollment consumed the current one)."""
    totp = pyotp.TOTP(secret)
    interval = totp.interval
    now = time.time()
    remaining = interval - (now % interval)
    time.sleep(remaining + 0.5)
    return totp.now()


def _run_concurrently(n, fn):
    """Run fn(i) in n threads released simultaneously; return list of results."""
    barrier = threading.Barrier(n)
    results = [None] * n

    def runner(i):
        barrier.wait()
        try:
            results[i] = ("ok", fn(i))
        except Exception as exc:  # noqa: BLE001 — result classification, not handling
            results[i] = ("err", f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=runner, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return results


def test_concurrent_same_totp_code_single_use(pg):
    """N simultaneous logins with ONE TOTP code -> exactly one session."""
    engine, SessionLocal = pg
    user_id, secret, _codes = _make_mfa_user(SessionLocal, "totp-race@concurrency.test")
    code = _wait_next_step(secret)

    from backend.app.services.auth_service import AuthService

    def attempt(_i):
        db = SessionLocal()
        try:
            out = AuthService(db).login(
                email="totp-race@concurrency.test",
                password="StrongPassw0rd!",
                mfa_code=code,
            )
            return bool(out.get("access_token"))
        finally:
            db.close()

    results = _run_concurrently(_CONCURRENCY, attempt)
    successes = [r for r in results if r[0] == "ok" and r[1]]
    failures = [r for r in results if r[0] == "err"]
    assert len(successes) == 1, (
        f"replay guard is not concurrency-safe: {len(successes)} of "
        f"{_CONCURRENCY} concurrent logins with the SAME TOTP code succeeded: {results}"
    )
    assert len(failures) == _CONCURRENCY - 1


def test_concurrent_same_recovery_code_single_use(pg):
    """N simultaneous logins with ONE recovery code -> exactly one success."""
    engine, SessionLocal = pg
    user_id, secret, codes = _make_mfa_user(SessionLocal, "recovery-race@concurrency.test")
    recovery_code = codes[0]

    from backend.app.services.auth_service import AuthService

    def attempt(_i):
        db = SessionLocal()
        try:
            out = AuthService(db).login(
                email="recovery-race@concurrency.test",
                password="StrongPassw0rd!",
                mfa_code=recovery_code,
            )
            return bool(out.get("access_token"))
        finally:
            db.close()

    results = _run_concurrently(_CONCURRENCY, attempt)
    successes = [r for r in results if r[0] == "ok" and r[1]]
    assert len(successes) == 1, (
        f"recovery-code consumption is not atomic: {len(successes)} of "
        f"{_CONCURRENCY} concurrent uses of the SAME code succeeded: {results}"
    )
    # And the code is really spent: a sequential retry must fail too.
    db = SessionLocal()
    try:
        from backend.app.core.exceptions import AuthenticationError

        with pytest.raises(AuthenticationError):
            AuthService(db).login(
                email="recovery-race@concurrency.test",
                password="StrongPassw0rd!",
                mfa_code=recovery_code,
            )
    finally:
        db.close()


def test_concurrent_enrollment_confirm_single_codeset(pg):
    """N simultaneous verify_mfa_setup with the same code -> ONE recovery-code set."""
    engine, SessionLocal = pg
    from backend.app.services.auth_service import AuthService
    from backend.app.models.user import MFABackupCode, User

    db = SessionLocal()
    try:
        svc = AuthService(db)
        svc.register(
            email="enroll-race@concurrency.test",
            password="StrongPassw0rd!",
            full_name="Enroll Race",
        )
        user = svc.user_repo.get_by_email("enroll-race@concurrency.test")
        secret = svc.setup_mfa(user)["secret"]
        user_id = user.id
    finally:
        db.close()

    code = _wait_next_step(secret)

    def attempt(_i):
        s = SessionLocal()
        try:
            u = s.query(User).filter(User.id == user_id).first()
            out = AuthService(s).verify_mfa_setup(u, code)
            return len(out["backup_codes"])
        finally:
            s.close()

    results = _run_concurrently(_CONCURRENCY, attempt)
    successes = [r for r in results if r[0] == "ok"]
    assert len(successes) == 1, (
        f"enrollment confirm is not serialized: {len(successes)} of "
        f"{_CONCURRENCY} concurrent confirms succeeded (each mints a code set): {results}"
    )
    # DB truth: exactly ONE set of recovery codes exists.
    db = SessionLocal()
    try:
        count = db.query(MFABackupCode).filter(MFABackupCode.user_id == user_id).count()
        assert count == 10, f"expected exactly 10 recovery codes, found {count}"
    finally:
        db.close()
