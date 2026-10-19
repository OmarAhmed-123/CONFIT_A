# CONFIT_A — External Integration Verification

**Date of record:** 2026-10-19 · **Branch:** `fix/wizard-reappearing` · **Run against:** the operator's credential set

**Tool:** `backend/scripts/verify_provider_credentials.py` — in-repo, read-only, least-privilege.

```bash
set -a; source ~/.env; set +a
PYTHONPATH=. python3 backend/scripts/verify_provider_credentials.py --json /tmp/report.json
```

**Status vocabulary:** `ok` · `auth_failed` · `unreachable` · `http_error` · `endpoint_unknown` · `shape_only` · `not_configured` · `skipped`

**Failure classes used in this document:** *bad key* · *not configured* · *provider error* · *read-only check not possible*.

> No credential value appears anywhere in this file, in the report, or in the tool's output. The tool prints only the variable **name**, an 8-character SHA-256 fingerprint, and a verdict. Fingerprints exist so that two slots holding the *same* value are visible; they are not reversible and are not a secret.

---

## 1. Summary

| Verdict | Count |
|---|---|
| `ok` | **30** |
| `shape_only` | **5** |
| `skipped` | **3** |
| `endpoint_unknown` | **3** |
| `not_configured` | **15** |
| `auth_failed` | **0** |

Zero credentials were rejected. Every configured credential either answered a read-only call or is classified below with the reason a read-only call was not possible.

---

## 2. Per-service results

| Provider | Capability | Env name | Result | Failure class | Latency (ms) |
|---|---|---|---|---|---|
| nvidia | kimi-k3 | `NVIDIA_API_KEY_KIMI_K3` | `ok` | — | 371 |
| nvidia | glm-5.3 | `NVIDIA_API_KEY_GLM_5_3` | `ok` | — | 49 |
| nvidia | glm-5.3-flash | `NVIDIA_API_KEY_GLM_5_3_FLASH` | `ok` | — | 57 |
| nvidia | muse-glimmer-30b | `NVIDIA_API_KEY_MUSE_GLIMMER_30B` | `ok` | — | 57 |
| nvidia | kumo-relational | `NVIDIA_API_KEY_KUMO_RELATIONAL` | `ok` | — | 51 |
| nvidia | nemotron-voicechat | `NVIDIA_API_KEY_NEMOTRON_VOICECHAT` | `ok` | — | 106 |
| nvidia | legacy shared key | `NVIDIA_API_KEY` | `ok` | — | 61 |
| nvidia | 13 key names read by no slot | — | `shape_only` | read-only check not possible | — |
| nvidia | legacy chat key | `NVIDIA_CHAT_KEY_2` | `not_configured` | not configured | — |
| openai | chat + embeddings | `OPENAI_API_KEY` | `ok` | — | 949 |
| gemini | vision + stylist | `GEMINI_API_KEY` | `ok` | — | 609 |
| groq | fast chat failover | `GROQ_API_KEY` | `ok` | — | 322 |
| unorouter | model gateway | `UNOROUTER_API_KEY` | `ok` | — | 755 |
| neon | primary app database (`confit_fixverify`) | `DATABASE_URL` | `ok` | — | 66 |
| neon | production owner role (`neondb`) | `DATABASE_URL_OWNER_NEONDB` | `ok` | — | 2 |
| neon | production app role (`neondb`) | `DATABASE_URL_APP_NEONDB` | `ok` | — | 2 |
| neon | fixverify owner role | `DATABASE_URL_OWNER` | `ok` | — | 2 |
| neon | fixverify app read-write role | — | `not_configured` | not configured | — |
| s3 | Neon S3 / AWS | `AWS_ACCESS_KEY_ID` | `ok` | — | 80 |
| s3 | RunPod S3 | `RUNPOD_S3_ACCESS_KEY` | `shape_only` | read-only check not possible | — |
| brevo | transactional email (API) | `BREVO_API_KEY` | `ok` | — | 769 |
| brevo | **sender / domain verification** | `BREVO_API_KEY` | `ok` — 1 active sender | — | 639 |
| smtp | outbound mail (handshake + AUTH) | `SMTP_HOST` | `ok` | — | 380 |
| resend | transactional email (API) | `RESEND_API_KEY` | `ok` | — | 370 |
| fx | exchangerate.host | `EXCHANGERATE_API_KEY` | `ok` | — | 557 |
| fx | fixer.io | `FIXER_API_KEY` | `ok` | — | 248 |
| sentry | error tracking | `SENTRY_DSN_TOKEN` | `skipped` | read-only check not possible | — |
| glitchtip | error tracking (self-hosted) | `GLITCHTIP_TOKEN` | `skipped` | read-only check not possible | — |
| betterstack | uptime monitoring | `BETTERSTACK_TOKEN` | `ok` | — | 466 |
| huggingface | model weights + inference | `HF_TOKEN` | `ok` | — | 317 |
| kaggle | datasets / notebooks | `KAGGLE_API_TOKEN` | `ok` | — | 293 |
| baseten | serverless GPU | `BASETEN_API_KEY` | `ok` | — | 543 |
| cerebrium | serverless GPU | `CEREBRIUM_TOKEN` | `endpoint_unknown` | provider error (HTTP 502) | 128 |
| runpod | GPU pods + storage | `RUNPOD_API_KEY` | `ok` | — | 428 |
| modal | VTON + VLM workers | `MODAL_TOKEN_ID` | `shape_only` | read-only check not possible | — |
| fitroom | external try-on renderer | `FITROOM_API_KEY` | `endpoint_unknown` | provider error (HTTP 503) | 326 |
| payments | PSP (live card / wallet charging) | — | `skipped` | not configured | — |
| vercel | deploy target | `VERCEL_TOKEN` | `ok` | — | 209 |
| github | repository + CI | `GITHUB_TOKEN` | `ok` | — | 235 |
| confit-hub | internal hub API | `CONFITHUB_API_KEY` | `shape_only` | read-only check not possible | — |
| dynu | DNS records | `DYNU_API_KEY` | `ok` | — | 299 |
| dnshe | DNS records | `DNSHE_API_KEY` | `endpoint_unknown` | provider error (HTTP 404) | 929 |
| digitalplat | DNS + domains | `DIGITALPLAT_API_KEY` | `shape_only` | read-only check not possible | — |

---

## 3. What the non-`ok` rows actually mean

### 3.1 Payments — no live charge path exists (highest-severity finding)

`backend/app/providers/payment/orchestrator.py` declares `LIVE_PSP_ADAPTERS: Dict[str, Any] = {}` — empty. There is no Stripe, Paymob, Tabby or Tamara adapter, and no PSP credential in the environment. Spec `012-payments-psp-seam` is a **seam**, not an implementation.

**Consequence:** checkout runs in demo mode. The product cannot take a real payment. This is not a credential problem and buying a key would not fix it — the adapter does not exist. Classified **not configured**, deliberately not "bad key", because a reader who sees "bad key" would go looking for a key to rotate.

No balance/account call was attempted: with no adapter there is no documented read-only endpoint, and inventing one would produce a verdict that means nothing.

### 3.2 Thirteen NVIDIA keys are configured under names nothing reads

The operator supplied 19 `NVIDIA_*` keys. The pool (`backend/app/providers/nvidia/keypool.py`) reads 19 canonical slots (`NVIDIA_KEY_<MODEL>`) plus the `NVIDIA_API_KEY_<MODEL>` alias. **Six** of the supplied names match a slot. **Thirteen do not**, because they were shortened:

| Supplied name | Slot the app reads |
|---|---|
| `NVIDIA_API_KEY_NEMOTRON_3_ULTRA` | `NVIDIA_KEY_NEMOTRON_3_ULTRA_550B_A55B` |
| `NVIDIA_API_KEY_NEMOTRON_3_SUPER` | `NVIDIA_KEY_NEMOTRON_3_SUPER_120B_A12B` |
| `NVIDIA_API_KEY_NEMOTRON_35_LIGHTNING` | `NVIDIA_KEY_NEMOTRON_3_5_LIGHTNING_30B_A3B` |
| `NVIDIA_API_KEY_NEMOTRON_3_NANO_OMNI` | `NVIDIA_KEY_NEMOTRON_3_NANO_OMNI_30B_A3B_REASONING` |
| `NVIDIA_API_KEY_CONTENT_SAFETY` | `NVIDIA_KEY_NEMOTRON_3_5_CONTENT_SAFETY` |
| `NVIDIA_API_KEY_NEMOTRON_3_EMBED` | `NVIDIA_KEY_NEMOTRON_3_EMBED_1B` |
| `NVIDIA_API_KEY_RIVA_TRANSLATE` | `NVIDIA_KEY_RIVA_TRANSLATE_4B_INSTRUCT_V2` |
| `NVIDIA_API_KEY_DIFFUSIONGEMMA` | `NVIDIA_KEY_DIFFUSIONGEMMA_26B_A4B_IT` |
| `NVIDIA_API_KEY_GEMMA_4_31B` | `NVIDIA_KEY_GEMMA_4_31B_IT` |
| `NVIDIA_API_KEY_DEEPSEEK_V41_FLASH` | `NVIDIA_KEY_DEEPSEEK_V4_1_FLASH` |
| `NVIDIA_API_KEY_LAGUNA_XS` | `NVIDIA_KEY_LAGUNA_XS_2_1` |
| `NVIDIA_API_KEY_ISING_CALIB_A` | `NVIDIA_KEY_ISING_CALIBRATION_1_5_31B` |
| `NVIDIA_API_KEY_ISING_CALIB_B` | `NVIDIA_KEY_ISING_CALIBRATION_1_5_31B_2` |

**Consequence:** those thirteen are inert at runtime. Content-safety, embeddings and the calibration models are among them, so features that assume a dedicated model silently fall back. The keys are valid; the *names* are the defect. Renaming is a config change, not a code change — but it must be deliberate, and the report now states it instead of printing a bare "not configured".

### 3.3 Sentry / GlitchTip — a project key is not a DSN

`SENTRY_DSN_TOKEN` (71 chars) and `GLITCHTIP_TOKEN` (64 chars) are bare strings with no host and no project id. The SDK needs the full `https://<key>@<host>/<project>` form, and the read-only API needs an *auth token*, which is a different credential. Both marked `skipped` with that reason rather than guessed at.

### 3.4 Modal, confit-hub, DigitalPlat, RunPod S3 — no callable read-only surface

- **Modal** has no public REST endpoint (gRPC + CLI); token id + secret + secure token are present and paired. Verify with `modal app list`.
- **confit-hub** and **DigitalPlat** have credentials but no endpoint declared anywhere in the repo.
- **RunPod S3** has a key pair but **no endpoint of its own** configured. It is deliberately *not* tested against the AWS host — see §4.2.

### 3.5 Cerebrium, FitRoom, DNSHE — the provider answered, but not usefully

| Provider | Answer | Reading |
|---|---|---|
| Cerebrium | HTTP 502 Bad Gateway | their read-only endpoint did not serve; nothing established about the key |
| FitRoom | HTTP 503 "unconditional drop overload" | provider-side overload; nothing established about the key |
| DNSHE | HTTP 404 (HTML page) | the configured endpoint path does not exist; the read-only surface is undocumented here |

None of these is evidence that the credential is bad, so none is classified *bad key*.

---

## 4. Defects this slice found and fixed

Each carries a regression test that **fails on the previous code** (verified: 9 of the new tests fail against the pre-change script).

### 4.1 Wrong slot names reported configured credentials as absent
`DATABASES` assumed `DATABASE_URL_NEONDB_OWNER`; the operator's file stores `DATABASE_URL_OWNER_NEONDB`. Four of five database rows printed "not configured" for DSNs that were configured — the report was at 1/5 accurate. Both spellings are now accepted; the live run resolves **4/5**.

### 4.2 RunPod's key was presented to AWS's endpoint
Both S3 targets shared `AWS_ENDPOINT_URL_S3`, so a RunPod key was sent to the AWS host and rejected → reported `auth_failed`, i.e. "your credential is bad". Each target now carries its own endpoint; a missing one produces `shape_only` ("no endpoint of its own"), never a false rejection.

### 4.3 Brevo sender check read the wrong payload shape
`GET /v3/senders` answers `{"senders": [...]}`. An intermediate version read only a bare list, so an account with **one active sender** was reported as having **none** — a false FAIL on the mail path. Both shapes are handled, and an unrecognised shape now reports `endpoint_unknown` instead of being read as zero.

### 4.4 Credentials present under an unread spelling were reported as absent
`GLITCHTIP_TOKEN`, `CONFITHUB_API_KEY` and `SENTRY_DSN_TOKEN` were invisible to the tool (it looked only for `GLITCHTIP_KEY`, `CONFIT_HUB_API_KEY`, `SENTRY_AUTH_TOKEN`). All are now recognised, and a DSN token is reported as a *gap with a reason* rather than as "configured".

### 4.5 No PSP probe existed
The tool had no coverage of the payments seam at all — the single most consequential integration for a commerce product. Added as its own group, read-only by construction, asserting in a test that it contains no mutating call.

---

## 5. What this run does NOT establish

- **No message was sent.** SMTP is handshake + AUTH only; Brevo and Resend are `GET`s. A "valid key" here does not prove deliverability — only §3's sender row speaks to that, and it says one sender is active.
- **No write, upload, DNS change or GPU job** was performed anywhere.
- **No production data was mutated.** The four Neon probes each ran `select current_database(), version()` and nothing else.
- **Model IDs were not deep-validated.** The NVIDIA probe confirms the catalogue is reachable *with that key*; it does not prove each model slug is still served. Deprecation checking needs a per-model inference call, which is not read-only-free (it bills).
- **Latency is one sample**, from this workspace. It is evidence the call worked, not a performance measurement.

---

## 6. Reproducing

```bash
set -a; source <your env file>; set +a
PYTHONPATH=. python3 backend/scripts/verify_provider_credentials.py            # human report
PYTHONPATH=. python3 backend/scripts/verify_provider_credentials.py --json r.json
PYTHONPATH=. python3 backend/scripts/verify_provider_credentials.py --only nvidia neon --quiet
```

Exit codes: `0` every configured credential answered · `1` a configured credential failed · `2` nothing configured.

The report is written to a path you choose and is **not** committed — it contains names and fingerprints, which are safe, but it is run output, not source.
