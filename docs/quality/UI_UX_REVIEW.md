# UI / UX Review — 2026-10-29

Evidence: `docs/qa/evidence/review_20261029/{en,ar}_{desktop,mobile}_{home,closet,stylist}.png` (desktop 1440×900, mobile 390×844, deterministic backend, real sign-in), plus the browser E2E screenshots. Automated measurements in `keyboard_and_viewport_findings.json`. This is an engineering review, not a designer sign-off.

## Journey verified (browser E2E, EN + AR, 24/24 checks)

Sign in → add garment (manual form) → stylist request → labelled result → save look → appears in *My Looks*. Session cookie `confit_token` set httpOnly; `dir` switches correctly; zero uncaught page errors.

## Findings

| ID | Screen | Finding | Severity | Status |
|---|---|---|---|---|
| UX-1 | Wardrobe (mobile) | The stylist/closet tool sits **below two full-height marketing carousels** ("Reuse owned pieces…", "Rotating capsule view"); on 390 px the user scrolls ~3 screens before reaching their closet or the stylist form (`en_mobile_stylist.png`) | High | Verified; proposed: collapse carousels on `?tab=` deep links or move them below the tool |
| UX-2 | Wardrobe (mobile) | Tab bar (My Closet / AI Stylist / My Looks / Gap Analysis / Mood Boards) wraps to two rows in AR, one row of five tightly spaced chips in EN | Medium | Verified; proposed horizontal scroll with snap |
| UX-3 | Stylist result | Source badge ("Rule-based match — not AI" / Granite) is visible and localised; items carry a per-item "matched by rule" chip; limitation notice shown — honesty requirements met ✔ | — | Verified OK |
| UX-4 | Closet cards (mobile) | Each card ≈ 1 screen tall because of the placeholder image box; 4 items = 4 screens | Medium | Verified; proposed 2-column grid at ≥ 360 px |
| UX-5 | All | Interactive targets smaller than 24×24 CSS px: EN desktop 8, EN mobile 12, AR mobile 12, AR desktop 1 (carousel dots / pagination). WCAG 2.2 2.5.8 minimum is 24 px | Medium | Verified by measurement; see accessibility audit A11Y-3 |
| UX-6 | Home / Wardrobe | No horizontal overflow at 390 px in either language ✔ | — | Verified OK |
| UX-7 | Add garment | Free-text colour; unknown words now show "Unknown colour / لون غير محدد" instead of silently becoming Black ✔ (this pass) | — | Verified (E2E "Olive"/"زيتوني" → Green) |
| UX-8 | Add garment | Colour field has no suggestions; typing "Olive" works only because the alias exists; a datalist of the 20 families would reduce Unknowns | Low | Proposed |
| UX-9 | Stylist form | Occasion is a `<select>`; pressing Enter on it does not submit (expected HTML behaviour); the submit button is the 6th Tab stop with a visible ring ✔ | Info | Verified |

## Not reviewed
* Checkout / commerce flows, brand back-office, mood boards (out of this pass's scope).
* Visual design consistency against a design system (none in repo).
