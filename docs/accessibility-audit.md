# Accessibility audit — stylist feature (index)

Full report: **`docs/qa/STYLIST_A11Y_REPORT.md`** (method, raw Orca transcript,
per-state axe results, update 2026-10-27). Platform-wide context:
`docs/qa/FINAL_A11Y_AUDIT_AND_RELEASE_APPROVAL.md`,
`docs/ACCESSIBILITY_AND_REAL_WORLD_QA_PROTOCOL.md`.

| Check | Result | Evidence |
|---|---|---|
| axe-core, 8 page states × EN/AR (form, result, saved, looks) | **0 violations**, Chromium + Firefox | `docs/qa/stylist_a11y_report.json` |
| Component axe in unit tests (`wardrobeStylistPanel.test.tsx`, incl. *Colours to avoid* and the *Added by rules* badge) | 0 violations EN and AR/RTL | vitest (901 at 3f2fe70) |
| Keyboard: all 23 form stops reachable, no traps; result actions reachable | PASS | report §Results |
| Focus management after generation → result `<h3 tabindex=-1>` (WCAG 2.4.3) | PASS EN/AR | report |
| Live regions on save (WCAG 4.1.3) | PASS EN/AR | report; re-observed in browser E2E 2026-10-29 ("Saved to your wardrobe looks (#2)…" / «حُفظت ضمن إطلالات خزانتك (رقم 3)…») |
| `dir=rtl` for Arabic | PASS | E2E 2026-10-29 `dir: "rtl"` |
| Provenance/fallback badge not colour-only (text + icon) | PASS | screenshots `docs/qa/evidence/local_e2e_20261029/` |
| CI a11y gate | green at 3f2fe70 | GitHub Actions |
| **Orca** (real screen reader), EN journey, Firefox | PARTIALLY VERIFIED (one defect found and fixed) | report transcript |
| **NVDA / JAWS / VoiceOver / TalkBack** manual sessions | **NOT PERFORMED** — no Windows/macOS/mobile in this environment; nothing is claimed | — |
| Arabic real-AT transcript | **NOT PERFORMED** | — |

Verdict unchanged: automated **PASS**; manual assistive-technology review (incl.
Arabic) **outstanding** and listed in `release-readiness.md` §G.
