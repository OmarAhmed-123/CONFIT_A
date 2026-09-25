# Rate-limit bucket identity — who pays for a request

**Status:** implemented app-side 2026-09-25; deployment requirement recorded below.
**Found by:** the independent consumer sweep (§34), after the D-2/D-3/D-4 fixes, while
probing for a rate-limit bypass.

## The measurement that started this

The limiter keyed requests on `x-real-ip` and, failing that, on the **left-most**
`X-Forwarded-For` entry. Against the running API, three requests carrying three
different spoofed `X-Forwarded-For` values produced **three separate buckets** in
Redis (`LIMITS:LIMITER/ip:203.0.113.7/…`, `…/ip:203.0.113.8/…`, `…/ip:198.51.100.9/…`).
The identity that decides whether the AI-cost quota applies was therefore chosen by
the caller.

This codebase had already documented the hazard in another file —
`backend/app/core/request_context.py` states that the left-most entry "is
client-supplied and spoofable" and prefers the right-most hop for audit rows. Two
contradictory notions of "who is calling" cannot both be right; the limiter is the
one that spends money, so it now follows one closed-by-default policy.

## The two layers (both were measured)

| Layer | Where | Default | Effect measured |
| --- | --- | --- | --- |
| Application | `core/rate_limit.py::_client_ip` | was: `x-real-ip` → **left-most** XFF → socket | caller-controlled bucket (5 rotated headers → 5 buckets) |
| ASGI server | `uvicorn --proxy-headers` / `FORWARDED_ALLOW_IPS` | `127.0.0.1` | if the peer address is trusted, uvicorn **rewrites `scope["client"]`** from XFF before the app runs, so the application cannot see the spoof — 5 rotated headers → 5 buckets with the app fix already in place |

That second row is why the first fix appeared not to work. An app-level policy alone
cannot close a hole that the server opens underneath it. With the server layer closed
(`--forwarded-allow-ips=`) the same probe produced **exactly 1 bucket**.

## Fix 1 — application policy (in place)

`core/rate_limit.py::_client_ip` now resolves identity as:

1. **On the hosting platform** (`VERCEL` in the environment — the same signal
   `core/database.py` uses): `x-vercel-forwarded-for`, then `x-real-ip`, then the
   **right-most** `x-forwarded-for` hop. Vercel documents that it overwrites
   `x-forwarded-for` to prevent IP spoofing, and that `x-vercel-forwarded-for` is the
   copy that survives an upstream proxy rewriting XFF.
2. **Off-platform:** headers are trusted **only** when the socket peer is inside
   `TRUSTED_PROXY_IPS` (comma-separated CIDRs); then the right-most hop is used.
3. Otherwise the socket peer.

The left-most entry is never used at any trust level, every candidate must validate as
an IP address (so junk cannot become a bucket), and an unresolvable identity collapses
to the single shared bucket `unknown` — failing closed, not open.

## Fix 2 — deployment requirement (operator action)

The ASGI server must not trust forwarded headers from a peer that a caller can be. For
any deployment that is not Vercel, the start command must set the trust list
explicitly, e.g. `uvicorn … --forwarded-allow-ips=<proxy address>` or the
`FORWARDED_ALLOW_IPS` environment variable. Two consequences, both operational:

* leaving uvicorn's default means *anything that can reach the app from `127.0.0.1`
  can choose its own quota bucket* (a sidecar proxy on the same host is the common
  case, and then the proxy decides: it must **set** `X-Forwarded-For` to the client —
  `proxy_set_header X-Forwarded-For $remote_addr` — and must never use
  `$proxy_add_x_forwarded_for`, which preserves the client's own value as the
  left-most entry);
* setting `--forwarded-allow-ips=` (trust nothing) is safe but keys every shopper on
  the proxy address, i.e. one shared quota for the whole internet. That is a
  deliberate trade-off, not a default to adopt blindly.

## Topology assessment (measured vs assumed)

| Topology | XFF trustworthiness | State |
| --- | --- | --- |
| Vercel production | platform **overwrites** XFF (documented) | application branch 1 applies; **not proven exploitable**, and the deployment probe below is the evidence step |
| Local dev / direct-to-app | peer is `127.0.0.1`, uvicorn default trusts it | caller can choose its bucket — demonstrated; no security boundary exists in this topology, which is why it is not claimed as a production defect |
| Container with a same-host proxy (`Dockerfile`, `backend/Dockerfile`, HF-Spaces-style port 7860) | depends on the proxy's header handling and `FORWARDED_ALLOW_IPS` | **UNVERIFIED** — the container start commands still rely on the server default; see follow-up |

## Evidence

* `CONFIT_evidence/49-rate-limit-bucket-identity.txt` — before/after, both layers,
  with bucket names and counts.
* `CONFIT_evidence/49-rate-limit-identity-mutation.txt` — mutation control: restoring
  the left-most-trust rule → **11 failed / 9 passed** across the identity and
  rate-limiting suites, then byte-identical restore and **20 passed**.
* `backend/tests/test_rate_limit_identity.py` — 12 tests: spoofed single value, spoofed
  chain, spoofed `x-real-ip`, junk values, missing peer, platform header precedence,
  right-most-hop rule, trusted/untrusted self-hosted peers, IPv6 and over-long values,
  plus a behavioural test that rotates the header across 21 requests and still demands
  a 429.

An existing guard in `backend/tests/test_rate_limiting.py`
(`test_the_key_isolates_callers_by_token_not_only_by_address`) pinned the old
expectation directly. It was not deleted or weakened: its intent — shoppers behind one
edge do not share a bucket, and none of them can choose theirs — is now asserted
through the trusted-proxy path, and the untrusted case is asserted alongside it. Local
verification after the change: backend **2739 passed / 4 skipped**, vitest
**575 passed (43 files)**, `tsc --noEmit` clean, i18n gate passed.

## Follow-up (recorded, not silently fixed)

1. **Deployment probe (production acceptance):** send the harmless quota probe with a
   rotated `X-Forwarded-For` and confirm the 429 still arrives at the same count. If it
   does not, the platform branch is not doing what the documentation promises and the
   claim becomes `UNVERIFIED` rather than assumed.
2. **Container start commands:** decide and verify `FORWARDED_ALLOW_IPS` for the
   container targets before claiming the limit is per-shopper there.
3. The per-caller cooldown and duplicate-suppression gaps recorded in
   `docs/STYLIST_PROMPT_BOUND_DECISION.md` are unchanged by this work.
