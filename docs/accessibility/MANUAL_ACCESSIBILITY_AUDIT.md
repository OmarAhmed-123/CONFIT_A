# Manual Accessibility Audit — 2026-10-29

Scope: wardrobe page (closet tab, AI stylist tab, upload dialog, auth modal), EN and AR. Method: **keyboard-only operation driven through a real Chromium via Playwright, recording the live DOM focus state after each key press** (`docs/qa/evidence/review_20261029/keyboard_and_viewport_findings.json`). Automated axe scanning is already a CI gate (`stylist-browser-gate`) and is not repeated here.

**Screen-reader testing (NVDA / VoiceOver / Orca) was NOT performed in this pass** — no assistive technology was run. The repo contains an Orca harness (`scripts/qa/orca_stylist_session.sh`) that requires a desktop session not available here. Marked BLOCKED, not passed.

## 1. Keyboard-only — results

| ID | Check | EN | AR | Evidence |
|---|---|---|---|---|
| KB-1 | Tab order in stylist form is logical (occasion → time → season → location → preferences disclosure → **Build my outfit** → next section) | PASS | PASS (same order; RTL layout does not reorder DOM) | `tab_order` arrays |
| KB-2 | Every focus stop shows a visible indicator (outline or focus ring) | PASS 9/9 | PASS 9/9 | `outline`/`boxShadow` true on each stop |
| KB-3 | Submit button reachable by Tab | PASS (stop 6 "Build my outfit") | PASS (stop 6 "ابنِ إطلالتي") | |
| KB-4 | Upload dialog opens with **Enter** on the trigger button | PASS | PASS | `dialog.opened_by_enter` |
| KB-5 | Focus moves into the dialog on open | PASS | PASS | `focus_moved_into_dialog` |
| KB-6 | **Escape** closes the dialog | PASS | PASS | `escape_closes` |
| KB-7 | Focus returns to the trigger after close | PASS | PASS | `focus_restored` (before/after identical) |
| KB-8 | Result region announces without moving focus (`aria-live="polite"` on result section; `role="status"` on save status) | PASS (code + DOM) | PASS | `WardrobeStylistPanel.tsx` L447/L690 |
| KB-9 | Auth modal: fields labelled (`#auth-email`, `#auth-password`), Enter submits | PASS | PASS | E2E login via keyboard Enter |

## 2. Findings

| ID | Finding | WCAG | Severity | Status |
|---|---|---|---|---|
| A11Y-1 | Onboarding modal appears on first visit over the wardrobe; it is dismissible with Escape (verified) but reappears per session until dismissed — keyboard users hit it on every tab deep link | 2.4.3 | Low | Verified; proposed persist dismissal in localStorage |
| A11Y-2 | Carousel pagination dots and prev/next controls are the first interactive elements on the wardrobe page before the tool; ~10 extra Tab stops to reach the closet on mobile | 2.4.1 | Medium | Verified; proposed skip link "Skip to my wardrobe" |
| A11Y-3 | 8–12 interactive targets under 24×24 px per viewport (carousel dots, pagination chevrons) | 2.5.8 (AA, 2.2) | Medium | Verified by measurement |
| A11Y-4 | `Unknown colour` label is now spoken instead of a misleading "Black" (fixed this pass) | 1.3.1 | — | Verified |

## 3. Blocked / not tested

| Item | Status | Why |
|---|---|---|
| Screen reader pass (NVDA + Chrome, VoiceOver + Safari, Orca + Firefox) | **BLOCKED** | no AT runtime in the sandbox; plan: run `scripts/qa/orca_stylist_session.sh` on a Linux desktop and the NVDA script in `docs/accessibility-audit.md §Plan` |
| 200 % zoom / reflow at 320 px | NOT TESTED | |
| Reduced-motion preference on carousels | NOT TESTED | |
| Colour contrast beyond axe's automated check | NOT TESTED manually | |

## 4. Conclusion
Keyboard operability of the audited flows is **PASS** in both languages with three medium/low findings (A11Y-1..3) that do not block the flow. Overall accessibility status remains **CONDITIONAL** until a screen-reader pass is executed.
