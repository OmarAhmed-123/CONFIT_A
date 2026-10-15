# Provider credentials — live verification

**Run:** 2026-10-14 · **Tool:** `backend/scripts/verify_provider_credentials.py` · **Verdict:**
**42 credentials answered, 2 rejected, 1 returned an error, 3 endpoint-unknown, 4 shape-only.**
No credential value appears in this document, in the tool's output, or in any commit — the report
carries names and an 8-character SHA-256 fingerprint only.

---

## 1 · Why this exists

`backend/scripts/verify_nvidia_models.py` re-verifies the NVIDIA NIM layer because "assertions
decay" — a model that was alive in August can be 410 Gone in September and nothing in CI notices.
Every other credential the operator supplied had no equivalent: databases, object storage, mail,
FX, uptime, error tracking, serverless GPU, DNS. This is that equivalent, and its first run paid
for itself (§3).

```bash
source ~/confit-secrets/load.sh                 # or any env file, exported
python3 backend/scripts/verify_provider_credentials.py
python3 backend/scripts/verify_provider_credentials.py --only nvidia neon --json /tmp/creds.json
python3 backend/scripts/verify_provider_credentials.py --quiet    # one summary line, for CI
```

Exit codes: `0` every configured credential answered · `1` a configured credential failed a live
probe · `2` nothing was configured at all.

**Safety, by construction.** Every probe is a `GET` or a protocol handshake: no mail is sent, no
object is uploaded, no DNS record is touched, no GPU job is started. Two tests enforce that — one
greps the tool's own source for `POST`/`PUT`/`PATCH`/`DELETE` and for `sendmail`, the other proves
that a rendered report cannot contain a supplied value. Secret values are never printed: the
fingerprint exists so that *the same* credential appearing in two slots is visible without either
value being revealed.

**Honesty.** Each probe reports only what it established:
`ok` (authenticated and answered) · `auth_failed` (reachable, credential rejected) ·
`unreachable` · `http_error` · `endpoint_unknown` (credential present, read-only surface not
verified) · `shape_only` (present and well-formed, not authenticated) · `not_configured`.
Nothing is inferred from the mere presence of a variable.

---

## 2 · The matrix

| Capability | Provider / slot | Verdict |
|---|---|---|
| Stylist, vision, safety, embeddings, translation | **NVIDIA NIM — 19 per-model keys** | `ok` · 19/19, catalogue reachable per slot key |
| Chat + embeddings | OpenAI | `ok` |
| Vision + stylist | Gemini (`GEMINI_API_KEY`) | `ok` |
| Fast chat failover | Groq | `ok` |
| Model gateway | Unorouter | `ok` |
| Application database (primary) | `DATABASE_URL` | **`auth_failed`** — endpoint reachable, login rejected |
| Neon project roles ×4 | `DATABASE_URL_NEONDB_*`, `DATABASE_URL_FIXVERIFY_*` | `ok` · PostgreSQL 16.15 (`neondb`, `confit_fixverify`) |
| Object storage | Neon S3 / AWS | `ok` · bucket list + `head_bucket` |
| Object storage | RunPod S3 | **`auth_failed`** — `InvalidAccessKeyId` |
| Transactional email | Brevo API | `ok` |
| Outbound mail | Brevo SMTP | `ok` · STARTTLS + AUTH (no message sent) |
| Transactional email | Resend | `ok` |
| FX rates | exchangerate.host | `ok` |
| FX rates | fixer.io | `ok` |
| Error tracking | Sentry | `ok` |
| Error tracking | GlitchTip | `shape_only` — a project key, not a DSN |
| Uptime monitoring | BetterStack | `ok` |
| Model weights / inference | Hugging Face | `ok` |
| Datasets | Kaggle | `ok` |
| Serverless GPU | Baseten | `ok` |
| Serverless GPU | **Cerebrium** | `endpoint_unknown` — HTTP 502 |
| GPU pods + storage | RunPod API | `ok` |
| VTON + VLM workers | Modal | `shape_only` — id+secret pair present |
| Deploy target | Vercel | `ok` (team-scoped token: `/v2/user` is not readable, project listing is) |
| Repository + CI | GitHub | `ok` |
| DNS records | Dynu | `ok` |
| DNS records | DNSHE | `endpoint_unknown` — read-only call came back 302 |
| DNS + domains | DigitalPlat | `shape_only` — no documented read-only endpoint |
| Internal hub | confitHub | `shape_only` — no endpoint declared in the repo |
| External try-on renderer | FitRoom | `endpoint_unknown` — 503 on the guessed surface |
| Legacy shared NVIDIA key | `NVIDIA_API_KEY` / `NVIDIA_CHAT_KEY_2` | `not_configured` (see §3) |

---

## 3 · The finding that mattered

**Nineteen live credentials were invisible to the product.**

The operator's env file names each per-model key after the *platform* credential
(`NVIDIA_API_KEY_KIMI_K3`). The pool reads the *slot* name (`NVIDIA_KEY_KIMI_K3`). Measured before
the fix, against the real env file:

```
configured ......... False
slots_present ...... 0/19
slots_missing ...... 19/19
pool_size .......... 0
```

Every consequence followed from that one mismatch: the stylist chain believed NVIDIA was
unavailable and fell through to providers it was not routed to, `MultiProviderAIOrchestrator.provider_status()`
reported `nvidia: {configured: false}`, `/health` reported an AI layer with no NVIDIA credentials,
and the nineteen keys spent nothing and did nothing. The keys were never the problem.

**The fix (`backend/app/providers/nvidia/keypool.py`)** accepts both namings and keeps the
canonical one authoritative:

- the mechanical rule derives `NVIDIA_API_KEY_<MODEL>` from `NVIDIA_KEY_<MODEL>`;
- four slots do **not** follow the rule and are listed explicitly rather than guessed — the supply
  distinguished two keys for one model (`…_ISING_CALIBRATION_A` / `_B`) and abbreviated two model
  names (`DIFFUSIONGEMMA_26B_A4B`, `NEMOTRON_3_NANO_OMNI_30B_A3B`);
- the `nvapi-` gate is unchanged: an alias is only read if it still looks like a key;
- the canonical name still wins when both are present, so an explicit deployment rename behaves
  exactly as before;
- `status()` now reports `aliased_slots` — **names only, never values** — so a renaming in an
  operator's file is visible in `/health` instead of silent.

Measured after the fix, same env file:

```
configured ......... True
slots_present ...... 19/19
slots_missing ...... []
pool_size .......... 19   (19 distinct credentials — the ISING pair stays two keys)
aliased_slots ...... 19   (every slot arrived under the operator's naming)
```

Two authorities were also corrected to agree with the pool rather than with the legacy shared key:
`ai_readiness._configured_providers()` (which gated NVIDIA on `NVIDIA_API_KEY` alone, and would
therefore have reported "not configured" *and* probed nothing) and
`MultiProviderAIOrchestrator.provider_status()`. Both now treat the pool as the authority and fall
back to the legacy names as the first key to test with — the legacy names are optional, not
required.

---

## 4 · Operator actions

| # | What | Why |
|---|---|---|
| 1 | Point `DATABASE_URL` at a role that authenticates | The primary DSN's endpoint answers but rejects its login. `DATABASE_URL_NEONDB_OWNER`, `DATABASE_URL_NEONDB_APP_RW`, `DATABASE_URL_FIXVERIFY_OWNER` and `DATABASE_URL_FIXVERIFY_APP_RW` all authenticate — two Neon projects (`neondb`, `confit_fixverify`), both PostgreSQL 16.15. **The app needs exactly one of them**; two projects means the product and the fix-verification harness can be separated deliberately rather than by accident. |
| 2 | Reissue the RunPod S3 key pair | `InvalidAccessKeyId` is a rejected credential, not a permission problem. The RunPod *API* key is valid and answered, so only the S3 pair is stale. |
| 3 | Check Cerebrium's API host | HTTP 502 on the documented-looking endpoint. The token format was accepted as a bearer token by the DNS/HTTP layer, but the service returned a gateway error — either the path moved or the account has no project yet. |
| 4 | Give GlitchTip a full DSN | The supplied value is a project key. The SDK needs `https://<key>@<host>/<project>`; the key alone cannot be turned into one here, and the app must not guess the host. |
| 5 | Give DNSHE the real read-only endpoint | The key+secret pair is present; the call returned 302 (a redirect to an auth or login flow), which means the endpoint path and/or auth header style in the tool is not the one this service uses. |
| 6 | Give FitRoom the render endpoint | Its surface is POST-only in the docs we have, so a read-only probe cannot authenticate. Worth one manual render rather than a guess. |
| 7 | `GEMINI_API_KEY_HEADER` does not hold an API key | Sent as `x-goog-api-key` it comes back "API key not valid". The name suggests it is the *header* to send the key in, not a second key. Left unprobed rather than guessed. |

Nothing above blocks the product: every capability those seven touch has a working credential
elsewhere, or is optional. They are recorded because a credential that is believed-good and is not
is exactly the class of defect this tool exists to surface.

---

## 5 · Mapping the two namings (names only)

The app reads the left column; the operator's file has the right column. Both now work — this table
is for anyone writing a `.env` by hand, and it contains no values.

| App name (canonical) | Also accepted | Model |
|---|---|---|
| `NVIDIA_KEY_NEMOTRON_3_ULTRA_550B_A55B` | `NVIDIA_API_KEY_NEMOTRON_3_ULTRA_550B_A55B` | nemotron-3-ultra-550b-a55b |
| `NVIDIA_KEY_NEMOTRON_3_SUPER_120B_A12B` | `NVIDIA_API_KEY_NEMOTRON_3_SUPER_120B_A12B` | nemotron-3-super-120b-a12b |
| `NVIDIA_KEY_NEMOTRON_3_5_LIGHTNING_30B_A3B` | `NVIDIA_API_KEY_NEMOTRON_3_5_LIGHTNING_30B_A3B` | nemotron-3.5-lightning-30b-a3b |
| `NVIDIA_KEY_NEMOTRON_3_NANO_OMNI_30B_A3B_REASONING` | `NVIDIA_API_KEY_NEMOTRON_3_NANO_OMNI_30B_A3B` | nemotron-3-nano-omni-30b-a3b-reasoning |
| `NVIDIA_KEY_NEMOTRON_3_5_CONTENT_SAFETY` | `NVIDIA_API_KEY_NEMOTRON_3_5_CONTENT_SAFETY` | nemotron-3.5-content-safety |
| `NVIDIA_KEY_NEMOTRON_3_EMBED_1B` | `NVIDIA_API_KEY_NEMOTRON_3_EMBED_1B` | nemotron-3-embed-1b |
| `NVIDIA_KEY_RIVA_TRANSLATE_4B_INSTRUCT_V2` | `NVIDIA_API_KEY_RIVA_TRANSLATE_4B_INSTRUCT_V2` | riva-translate-4b-instruct-v2 |
| `NVIDIA_KEY_KIMI_K3` | `NVIDIA_API_KEY_KIMI_K3` | kimi-k3 |
| `NVIDIA_KEY_GLM_5_3` | `NVIDIA_API_KEY_GLM_5_3` | glm-5.3 |
| `NVIDIA_KEY_GLM_5_3_FLASH` | `NVIDIA_API_KEY_GLM_5_3_FLASH` | glm-5.3-flash |
| `NVIDIA_KEY_DIFFUSIONGEMMA_26B_A4B_IT` | `NVIDIA_API_KEY_DIFFUSIONGEMMA_26B_A4B` | diffusiongemma-26b-a4b-it |
| `NVIDIA_KEY_GEMMA_4_31B_IT` | `NVIDIA_API_KEY_GEMMA_4_31B_IT` | gemma-4-31b-it |
| `NVIDIA_KEY_MUSE_GLIMMER_30B` | `NVIDIA_API_KEY_MUSE_GLIMMER_30B` | muse-glimmer-30b |
| `NVIDIA_KEY_DEEPSEEK_V4_1_FLASH` | `NVIDIA_API_KEY_DEEPSEEK_V4_1_FLASH` | deepseek-v4.1-flash |
| `NVIDIA_KEY_LAGUNA_XS_2_1` | `NVIDIA_API_KEY_LAGUNA_XS_2_1` | laguna-xs-2.1 |
| `NVIDIA_KEY_KUMO_RELATIONAL` | `NVIDIA_API_KEY_KUMO_RELATIONAL` | kumo-relational |
| `NVIDIA_KEY_NEMOTRON_VOICECHAT` | `NVIDIA_API_KEY_NEMOTRON_VOICECHAT` | nemotron-voicechat |
| `NVIDIA_KEY_ISING_CALIBRATION_1_5_31B` | `NVIDIA_API_KEY_ISING_CALIBRATION_A` | ising-calibration-1.5-31b |
| `NVIDIA_KEY_ISING_CALIBRATION_1_5_31B_2` | `NVIDIA_API_KEY_ISING_CALIBRATION_B` | ising-calibration-1.5-31b |

---

## 6 · What this run does **not** establish

- **Live inference, not just credentials.** The NVIDIA slots were verified against the free
  catalogue endpoint. Per-model behaviour claims stay with
  `backend/scripts/verify_nvidia_models.py --live`, which spends one small completion per model.
- **Modal.** No public REST surface exists, so the tool reports the pair as present and stops
  there. `modal app list` is the real check, and running it is a separate decision (it is the only
  probe that would touch GPU billing).
- **confitHub and DigitalPlat.** No endpoint is declared anywhere in this repo, so no probe can be
  honest about them yet.
- **Anything written.** No credential was rotated, no record was created, no message was sent. This
  is a read-only report, so "did it write?" is answered by the file it points at, not by this run.
