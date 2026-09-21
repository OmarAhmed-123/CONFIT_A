"""Safe production probe — MFA & data-rights E2E on the LIVE deployment.

Audit remediation (2026-09-21 identity/profile/MFA/data-rights report):
    "أضف اختبارات إنتاج آمنة لـMFA تشمل التفعيل، رمز خاطئ، رمز صحيح، وإلغاء
     التفعيل. وفّر حسابات اختبارية مؤقتة وموسومة مع تنظيف موثق."

What this script does — against the real production URL, with real HTTP:
 1. Registers a TAGGED, throwaway probe account
    (``probe+mfa-<ts>@confit-probe.example.com`` naming convention: clearly
    synthetic, never a real person, never reusable for marketing).
 2. Enrolls MFA: /mfa/setup -> local TOTP -> /mfa/verify (backup codes
    received).
 3. Proves the challenge: login WITHOUT a code -> 401 MFA_REQUIRED;
    login with a WRONG code -> 401; login with the CORRECT code -> 200.
 4. Proves replay protection: the code that just succeeded is replayed
    -> MUST be 401.
 5. Proves disable hardening: disable with password only -> 401
    MFA_CODE_REQUIRED; disable with password + fresh code -> 200; login
    without a code -> 200 again.
 6. GDPR export: fetches the archive, RECOMPUTES the sha256 over the
    canonical JSON and compares with the declared checksum.
 7. CLEANUP (documented, verified): DELETE /auth/account with the probe's
    own session; then proves the account is really gone (login -> 401).

The probe writes a JSON evidence report (timestamps, status codes,
checksums — never passwords/secrets/codes) to the path given by
``--report`` (default: ./mfa_probe_report.json).

Safety properties:
 - consumer self-registration only (the public surface); no admin
   credential, no direct DB access, no other user's data touched;
 - the account is deleted by the probe itself in the same run — cleanup
   failure is a FAILURE of the probe (exit non-zero), not a shrug;
 - all state lives in one tagged account; re-running is always safe.

Usage:
    python backend/scripts/production_mfa_data_rights_probe.py \
        [--base-url https://confit-a.vercel.app] [--report out.json]

Exit codes: 0 = every assertion held; 1 = an assertion failed;
            2 = probe could not run (network/env).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import sys
import time
from datetime import datetime, timezone

try:
    import httpx
    import pyotp
except ImportError as exc:  # pragma: no cover
    print(f"probe requires httpx + pyotp: {exc}", file=sys.stderr)
    sys.exit(2)

DEFAULT_BASE = "https://confit-a.vercel.app"
API = "/api/v1"


class ProbeFailure(AssertionError):
    pass


class Evidence:
    def __init__(self) -> None:
        self.steps: list[dict] = []
        self.started_at = datetime.now(timezone.utc).isoformat()

    def record(self, step: str, ok: bool, **detail) -> None:
        entry = {"step": step, "ok": ok, "at": datetime.now(timezone.utc).isoformat(), **detail}
        self.steps.append(entry)
        marker = "PASS" if ok else "FAIL"
        print(f"[{marker}] {step} {json.dumps(detail, default=str)[:160]}")

    def check(self, step: str, condition: bool, **detail) -> None:
        self.record(step, bool(condition), **detail)
        if not condition:
            raise ProbeFailure(step)

    def as_dict(self) -> dict:
        return {
            "probe": "mfa_data_rights",
            "started_at": self.started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "passed": all(s["ok"] for s in self.steps),
            "steps": self.steps,
        }


def canonical_bytes(data) -> bytes:
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode("utf-8")


def run(base_url: str, report_path: str) -> int:
    ev = Evidence()
    ts = int(time.time())
    email = f"probe+mfa-{ts}-{secrets.token_hex(4)}@confit-probe.example.com"
    password = "Pr0be!" + secrets.token_urlsafe(12)
    client = httpx.Client(base_url=base_url.rstrip("/") + API, timeout=45.0, follow_redirects=True)
    hdr: dict = {}
    deleted = False

    def login(mfa_code=None):
        payload = {"email": email, "password": password}
        if mfa_code is not None:
            payload["mfa_code"] = mfa_code
        return client.post("/auth/login", json=payload)

    try:
        # -- 1. tagged registration -------------------------------------
        r = client.post("/auth/register", json={
            "email": email, "password": password,
            "full_name": "MFA Probe (synthetic, auto-cleanup)",
        })
        ev.check("register tagged probe account", r.status_code == 201,
                 status=r.status_code, email=email)
        hdr = {"Authorization": f"Bearer {r.json()['access_token']}"}

        # -- 2. enroll ---------------------------------------------------
        r = client.post("/auth/mfa/setup", headers=hdr)
        ev.check("mfa setup returns secret", r.status_code == 200, status=r.status_code)
        secret = r.json()["secret"]
        totp = pyotp.TOTP(secret)
        r = client.post("/auth/mfa/verify", json={"code": totp.now()}, headers=hdr)
        ev.check("mfa verify enables + returns 10 backup codes",
                 r.status_code == 200 and len(r.json().get("backup_codes", [])) == 10,
                 status=r.status_code)
        backup_codes = r.json()["backup_codes"]

        # -- 3. challenge behaviour ---------------------------------------
        r = login()
        marker = (r.json().get("error", {}).get("details", {}) or {}).get("reason")
        ev.check("login without code -> 401 MFA_REQUIRED",
                 r.status_code == 401 and marker == "MFA_REQUIRED",
                 status=r.status_code, reason=marker)

        r = login(mfa_code="000000")
        ev.check("login with WRONG code -> 401", r.status_code == 401, status=r.status_code)

        time.sleep(31)  # fresh TOTP period — enrollment consumed the current step
        good_code = totp.now()
        r = login(mfa_code=good_code)
        ev.check("login with CORRECT code -> 200", r.status_code == 200, status=r.status_code)
        hdr = {"Authorization": f"Bearer {r.json()['access_token']}"}

        # -- 4. replay protection -----------------------------------------
        r = login(mfa_code=good_code)
        ev.check("REPLAYED code -> 401 (replay guard effective)",
                 r.status_code == 401, status=r.status_code)

        # -- 5. disable hardening -----------------------------------------
        r = client.post("/auth/mfa/disable", json={"password": password}, headers=hdr)
        marker = (r.json().get("error", {}).get("details", {}) or {}).get("reason")
        ev.check("disable with password ONLY -> 401 MFA_CODE_REQUIRED",
                 r.status_code == 401 and marker == "MFA_CODE_REQUIRED",
                 status=r.status_code, reason=marker)

        # a backup code is a valid second factor for disable (no TOTP wait)
        r = client.post("/auth/mfa/disable",
                        json={"password": password, "mfa_code": backup_codes[0]},
                        headers=hdr)
        ev.check("disable with password + recovery code -> 200",
                 r.status_code == 200, status=r.status_code)

        r = login()
        ev.check("after disable, login without code -> 200",
                 r.status_code == 200, status=r.status_code)
        hdr = {"Authorization": f"Bearer {r.json()['access_token']}"}

        # -- 6. GDPR export integrity ---------------------------------------
        r = client.get("/auth/gdpr-export", headers=hdr)
        ev.check("gdpr export -> 200", r.status_code == 200, status=r.status_code)
        body = r.json()
        integrity = body.get("export_integrity") or {}
        declared = integrity.get("checksum_sha256")
        recomputed = hashlib.sha256(canonical_bytes(body.get("data"))).hexdigest()
        ev.check("export checksum recomputed == declared",
                 declared is not None and recomputed == declared,
                 declared=declared, recomputed=recomputed,
                 canonical_bytes=integrity.get("canonical_bytes"))

        # -- 7. deletion step-up + documented cleanup -----------------------
        # Deletion without confirmation/password must be refused (round-2
        # hardening): a bare DELETE was previously enough.
        r = client.request("DELETE", "/auth/account", headers=hdr,
                           json={"confirm": "DELETE"})
        ev.check("delete WITHOUT password -> 401 (step-up enforced)",
                 r.status_code == 401, status=r.status_code)
        r = client.request("DELETE", "/auth/account", headers=hdr,
                           json={"confirm": "nope", "password": password})
        ev.check("delete with wrong confirm literal -> 401",
                 r.status_code == 401, status=r.status_code)
        r = client.request("DELETE", "/auth/account", headers=hdr,
                           json={"confirm": "DELETE", "password": password})
        ev.check("cleanup: DELETE with confirm+password -> 200",
                 r.status_code == 200, status=r.status_code)
        deleted = True
        r = login()
        ev.check("cleanup verified: probe login now 401 (account gone)",
                 r.status_code == 401, status=r.status_code)

        return 0
    except ProbeFailure:
        return 1
    except Exception as exc:  # noqa: BLE001
        ev.record("probe crashed", False, error=f"{type(exc).__name__}: {exc}"[:300])
        return 2
    finally:
        # Cleanup is part of the contract — try even after a failure.
        if not deleted and hdr:
            try:
                r = client.request("DELETE", "/auth/account", headers=hdr,
                                   json={"confirm": "DELETE", "password": password})
                ev.record("best-effort cleanup after failure",
                          r.status_code == 200, status=r.status_code)
            except Exception as exc:  # noqa: BLE001
                ev.record("best-effort cleanup after failure", False,
                          error=str(exc)[:200])
        report = ev.as_dict()
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, default=str)
        print(f"\nevidence report -> {report_path} (passed={report['passed']})")
        client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--report", default="mfa_probe_report.json")
    args = parser.parse_args()
    return run(args.base_url, args.report)


if __name__ == "__main__":
    raise SystemExit(main())
