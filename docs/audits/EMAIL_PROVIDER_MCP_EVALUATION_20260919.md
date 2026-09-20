# Transactional email: MCP Market discovery + provider decision
**Date:** 2026-09-19 · **Scope:** registration verification, password reset, email change, partner invitation and partner-decision mail for CONFIT_A
**Discovery source:** <https://mcpmarket.com/search?q=email> (inspected 2026-09-19)

---

## 1. What was searched and found

The MCP Market query `email` returns **20 email servers**. The eight most-installed / most relevant are listed below with what the listing and the server detail page actually claim. (Install counts are the numbers shown on the listing page; they are popularity signals, not reliability evidence.)

| # | Server | Author | What it is | Category | Installs |
|---|--------|--------|-----------|----------|---------|
| 1 | `mcp-email-server` (`email-27`) | Wh1isper | "IMAP and SMTP capabilities … comprehensive email management", headless + multi-account, interactive account config UI, custom TLS, **283 GitHub stars** | Developer Tools | 330 |
| 2 | `email` | ai-zerolab | "IMAP and SMTP functionality via an MCP server" | Other | 281 |
| 3 | `email-16` | codefuturist | "read, search, send, manage and analyze emails across multiple accounts using IMAP and SMTP" | Developer Tools | 111 |
| 4 | `email-1` | Shy2593666979 | "compose, send emails, and search for attachments within specified directories" | Other | 80 |
| 5 | `email-4` | TimeCyber | "manage and interact with various email services" | API Development | 75 |
| 6 | `email-17` | boutquin | 22 tools, multi-account IMAP/SMTP, **OAuth2**, "robust connection handling", threading/batch ops | Developer Tools | — |
| 7 | `email-24` | HardMCP | unified multi-provider mailbox operations | Developer Tools | — |
| 8 | `email-23` | pzanna | IMAP/SMTP exposed over **HTTP/SSE** | Developer Tools | — |

Remaining results (`email-2`, `email-3`, `email-5`, `email-6`, `email-11`…`email-15`, `email-20`…`email-22`, `email-25`) are the same shape: SMTP/IMAP/POP3 mailbox clients, some Gmail-API or 163.com specific, several Chinese-language-only.

## 2. Evaluation against the email requirements

| Criterion | Finding for the discovered MCP servers | Verdict |
|---|---|---|
| Reliability / production use | All are **developer/agent mailbox tools**; none publishes a delivery SLA, a status page or transactional-volume evidence. | ✗ |
| Real send | They do send (SMTP) — but only when a human mailbox credential is wired in. They are not an ESP. | ~ |
| Auth model | Per-user mailbox credentials + OAuth2 (some), stored/configured by the operator for an agent; not an account-level API key for a backend service. | ✗ |
| Transport | stdio (most), HTTP/SSE (some) — an **agent-protocol** transport, not an HTTPS REST contract a FastAPI worker can depend on. | ✗ |
| Secret handling | Operator-managed credential files/UI per account; no rotation/KMS story; the credentials are the human's mailbox password. | ✗ |
| Delivery semantics | SMTP hand-off at best. **No delivery/bounce/complaint webhooks**, no per-message idempotency key, no suppression-list handling. | ✗ |
| Idempotency | None documented in any listing — a retried tool call can duplicate a message. | ✗ |
| Error taxonomy | Free-text tool errors; no stable machine-readable failure classes (transient vs permanent vs blocked). | ✗ |
| Rate limits / retries | None documented; retry behaviour is whatever the agent decides. | ✗ |
| Observability | Agent-side logs only; nothing the backend can query per recipient/purpose. | ✗ |
| Sender/domain verification (SPF/DKIM/DMARC) | Out of scope for every one of them — they relay through the operator's mailbox, which also makes deliverability depend on a personal/corporate mailbox reputation. | ✗ |
| Transactional fit | Designed for inbox reading/organising by an assistant, not for "registration verification must arrive in seconds and be replay-safe". | ✗ |
| Vercel / FastAPI compatibility | stdio servers cannot run in a Vercel serverless request path; HTTP/SSE variants add a long-lived service with its own credential store. | ✗ |
| Operability | One more stateful service to run, patch and monitor, holding mailbox credentials. | ✗ |
| Licensing / cost / lock-in | Mixed licences (mostly MIT-style, some unstated); cost is the operator's mailbox. Lock-in is high in the sense that the integration surface is an agent protocol, not a mail API. | ~ |
| Documentation | Listing-level only for most; one (Wh1isper) has a real README + stars. | ~ |

## 3. Decision

**MCP servers are NOT used anywhere in the email path — not for send, not for status, not for retries.**

Reasons, in order of weight:

1. **Architecture violation.** The task's own constraint: *"MCP must NOT be a fake abstraction over email; no Frontend → LLM → MCP → 'pretend success' path. The backend must know real delivery status."* Every discovered server is invoked **by an agent**, i.e. the caller would be an LLM, and the outcome surface is agent prose — the exact anti-pattern that was forbidden. The backend could not assert `SUCCEEDED / FAILED / RETRYING / BLOCKED / UNVERIFIED` from an agent tool result.
2. **No delivery contract.** Nothing in the catalogue can answer the questions this requirement set demands (accepted? by whom? retryable? idempotent? bounce?). SMTP hand-off through a personal mailbox cannot even distinguish "relay accepted" from "domain rejects us".
3. **Credential blast radius.** Wiring a human mailbox password into an agent-accessible server puts account credentials one tool call away from an autonomy loop, for an auth-critical flow.
4. **Serverless incompatibility.** CONFIT_API runs on Vercel; stdio MCP servers cannot be reached from a serverless request path, and SSE variants re-introduce a stateful service holding mailbox credentials.

**What was implemented instead** (first-party, provider-agnostic, backend-owned):

```
AuthService / PartnerService  →  TransactionalEmailService (services/email_service.py)
                                      ├── adapter: smtp   (stdlib smtplib, STARTTLS/SSL)
                                      └── adapter: resend (HTTPS API — Vercel-safe)
                                 →  DeliveryResult {succeeded|failed|blocked|retrying|unverified}
                                 →  email_deliveries ledger + audit log + request correlation id
```

Properties the MCP route could not provide and this does: a unique `idempotency_key` per (purpose, token) so a double submit collapses into one message; a ledger row written from the **provider's own answer**; `BLOCKED` (no send attempted) instead of fabricated success when no provider is configured; SHA-256-only recipient storage; 2-attempt transient retry that never retries a relay rejection; header-injection-sanitised subjects; and honest, queryable status for the account owner (`GET /api/v1/auth/email-status`).

## 4. Where MCP *may* legitimately appear (operator-side only)

An operator may point an agent at a **support mailbox** MCP server (e.g. `email-17` for OAuth2 + multi-account, or `email-27`) to triage inbound `support@` mail. That is a human/ops workflow on a *different* mailbox: it must never be reachable from application code, never exposed to end users, and never used to claim a transactional email was delivered. No such integration exists in this change set.

## 5. Residual risk / follow-up

* Provider selection remains an **operator decision**: `EMAIL_PROVIDER=smtp` (any relay) or `EMAIL_PROVIDER=resend` (HTTPS, recommended on Vercel, see `backend/.env.example` §9). Until one is configured, auth email is honestly `BLOCKED` (HTTP 501 `FEATURE_NOT_CONFIGURED`) and third-party delivery is **UNVERIFIED**.
* If a future MCP email integration is proposed, the rule to keep: MCP may *read* an ops mailbox; it may never be the transport for a security-bearing message.
