# Screen-reader manual test protocol — brand memberships + try-on states

Status: **NOT RUN — no human screen-reader session has been performed for
these flows.** The CI accessibility gate (axe + component-level checks) and
the Playwright DOM journeys are automated structural checks; they are NOT a
screen-reader session and this PR does not claim otherwise.

## Environment contract

* Windows 11 + NVDA (current release) + Chrome, AND macOS + VoiceOver +
  Safari; Arabic pass with the OS language set to Arabic (RTL), English pass
  with EN. Record AT version + browser version + OS in every row.
* Staging URL with seeded demo brand (owner + 2 members + pending invites +
  one expired/one revoked invitation).

## Cases (log one row per case: steps / expected / observed / result / severity)

### Team management (`/account/brand` team panel)
1. Page title, landmarks, heading order; roster announced as a list; each
   member row: name, role, status, action-button names.
2. Open invite dialog: label, focus lands inside dialog, Tab order loops,
   Escape closes and returns focus to the opener.
3. Submit invalid email → error announced without moving focus; valid →
   success announcement + roster update announced.
4. Resend invitation → state change announced; revoke → confirmation dialog
   semantics; removal confirm → same dialog contract.
5. Last active owner: attempted removal → the `LAST_ACTIVE_OWNER` refusal is
   announced (not just displayed); retry control naming.
6. Loading state announced (progress/busy semantics), empty state readable.
7. Read-only member view: controls announced as disabled vs absent.

### Acceptance flow
8. Accept-link landing: heading + current status read; "complete sign-in to
   accept" guidance for logged-out users.
9. Invalid/expired/revoked/already-used tokens: each distinct message read
   verbatim from the server envelope.
10. After auth return: success/failure announcement; focus placement;
    back-navigation sanity.

### Errors & dynamic content
11. Server 409 (already a member) / 403 (not a member) / 500 (probe mode):
    message read + retry path named; no silent spinners.
12. Live-updating regions (status chips re-render on language switch): new
    value announced without keyboard-discovery.
13. EN↔AR toggle: `lang`/`dir` update announced; numerals and dates read in
    the target locale.

### Try-on sleeve-gate states (this PR's surface)
14. With `VTON_SLEEVE_GATE_MODE=observe` on staging: the sleeve chip text
    reads after render completion; verify the chip is reachable by reading
    order (it is `role="status"`, announced on arrival).
15. Enforced refusal (502 `VTON_SLEEVES_NOT_VERIFIED`): the job-failure card
    reads the refusal reason; ensure no image element is announced.

## Reporting format

| # | AT/browser/OS/locale | steps | expected | observed | result | severity | defect ref |
|---|---|---|---|---|---|---|---|

Blocking defects (announcements missing, focus trap broken, refusal silent)
require a fix + regression test + rerun of the affected rows before this
protocol can be marked PASS.

## What this sandbox DID instead (automated, labeled as such)

Where an automated AT-SPI probe was feasible it supplements but never
replaces rows 1–15; the results live in
`VTON_SLEEVE_GATE_READINESS_2026-10-18.md` §D and are explicitly NOT human
screen-reader validation.
