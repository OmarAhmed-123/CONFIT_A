# CONFIT_A — Accessibility (WCAG 2.2 AA), Assistive Technology & Real-World QA Protocol

**Document Version:** `2026-10-21`  
**Applicable Release Branch:** `feat/realworld-a11y-e2e-hardening` (integrating `origin/main` `66bb87f` + `origin/work/production-hardening` `ce74577`)  
**Executable Audit Harness:** `scripts/qa/run_live_orca_multiengine_a11y_audit.py`  
**Structured Machine-Readable Evidence:** `docs/qa/live_orca_multiengine_a11y_report.json`

---

## 1. Honesty & Evidence Standard

Every accessibility, localization, security, and production readiness statement in CONFIT follows a strict split between:

1. **Automated & Live Linux AT Verification (Executed & Machine-Proved in CI / Sandbox):**
   - **Live Desktop Screen Reader Stack (`Orca 48.1` + `AT-SPI2 2.56.2`):** Headed Desktop `Firefox 157.0` (`MOZ_ACCESSIBILITY_AT_SPI=1`, `GNOME_ACCESSIBILITY=1`) running over X11 (`Xvfb :99`), D-Bus (`org.a11y.Bus` / `org.a11y.atspi.Registry`), `speech-dispatcher`, `espeak-ng`, and live `gi.repository.Atspi` tree + event listeners (`object:state-changed:focused`, `document:load-complete`, `window:activate`).
   - **Multi-Engine Browser Rendering Matrix (`Playwright` + `axe-core` WCAG 2.2 AA):**
     - `Chromium 156.0.8078.4` (Blink — Google Chrome / Microsoft Edge / Android TalkBack engine)
     - `Firefox 157.0` (Gecko — Linux Orca / Windows NVDA reference engine)
     - `WebKit 27.2` (WebKit — Apple Safari / macOS & iOS VoiceOver engine)
   - **Full Automated Test Suites (`6,881` passing checks, `0` failures):**
     - Frontend Vitest: `155/155` files (`2,338/2,338` tests), `npm run i18n:check` (`0` baseline debt, `3,081` `en`/`ar` parity keys), production `tsc && vite build`.
     - Backend `pytest`: `4,537` passed (`0` failed) on SQLite + `6/6` PostgreSQL row-lock concurrency tests + `5/5` adversarial journey/BOLA/SSRF/CSV/GDPR tests on real `PostgreSQL 17.11`.

2. **Physical OS / Native Assistive-Technology Sign-Off Matrix (Requires Human Operator Hardware):**
   - Windows `NVDA` (`Firefox` / `Edge`) and `JAWS` (`Chrome` / `Edge`)
   - macOS `VoiceOver` (`Safari`) and iOS `VoiceOver` (`Mobile Safari` on iPhone)
   - Android `TalkBack` (`Chrome` on physical Android device)
   - Physical Windows High Contrast (`Contrast Themes`) hardware verification

---

## 2. Live Executed Results Summary (`2026-10-21`)

| Verification Dimension | Executed Tooling | Scope | Result |
|---|---|---|---|
| Desktop Screen Reader & AT-SPI2 Bus | `Xvfb :99` + `dbus-run-session` + `Orca 48.1` + `AT-SPI2 2.56.2` + `Firefox 157.0` | `8` core routes × `EN` (`dir="ltr"`) & `AR` (`dir="rtl"`) + PDP `NoPhotoFitModal` lifecycle | **PASS** (`52` live AT-SPI2 bus events captured; full accessible trees exposed) |
| Multi-Engine WCAG 2.2 AA (`axe-core`) | `Chromium 156.0.8078.4`, `Firefox 157.0`, `WebKit 27.2` | `48` route-engine-locale audits (`wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22aa`) | **PASS** (`0` critical / `0` serious violations across all 3 engines) |
| Arabic (`ar`) Screen-Reader `aria-label` Parity | Rendered DOM + AT-SPI2 attribute inspection in `ar` | All `[aria-label]` controls across all `8` routes × `3` engines | **PASS** (`0` English `aria-label` leaks — caught & fixed `11` carousel leaks on `/` + site-wide `ConfitIcons` `role="img"` leak) |
| Modal Focus Trap, Background Isolation & Focus Return | `useModalFocus.ts` + live Firefox PDP -> `NoPhotoFitModal` (`EN` & `AR`) | Open modal -> verify `role="dialog"[aria-modal="true"]`, `3` ancestor-sibling containers `aria-hidden="true"` (preserving live regions), focus inside modal -> `Escape` -> dialog closed, `aria-hidden` restored, focus back on trigger `<BUTTON>` | **PASS** (`EN` `"Find my size"` & `AR` `"اعرف مقاسي"`) |
| `320px` Mobile Reflow & `200%` Root Text Zoom | `Chromium`, `Firefox`, `WebKit` (`320×640` & `1280×800 @ 200%`) | `/`, `/catalog`, `/product/:slug`, `/fit-finder` in `EN` & `AR` | **PASS** (`0px` horizontal document overflow across every check) |
| Reduced Motion (`prefers-reduced-motion: reduce`) | All `3` browser engines + `CircularGallery` / motion primitives | OS media preference `reduce` active across audited routes | **PASS** (`window.matchMedia('(prefers-reduced-motion: reduce)').matches === true`, idle rotation disabled) |

---

## 3. Reproducible Command (One-Line Execution)

From the repository root on any Debian/Ubuntu runner with `xvfb`, `dbus-x11`, `at-spi2-core`, `orca`, `speech-dispatcher`, `espeak-ng`, and Playwright browsers installed:

```bash
xvfb-run -a -s "-screen 0 1440x900x24" \
  dbus-run-session -- bash -c '
    dbus-update-activation-environment DISPLAY XAUTHORITY 2>/dev/null || true
    exec .venv/bin/python scripts/qa/run_live_orca_multiengine_a11y_audit.py
  '
```

The command exits non-zero if **any** engine reports even a single `critical` or `serious` WCAG 2.2 AA violation or if **any** Arabic route emits an unlocalized English `aria-label`.

---

## 4. Physical OS Screen-Reader & Mobile Device Sign-Off Checklist (Operator Runbook)

Execute the exact 7-step script below on physical hardware prior to removing the beta accessibility notice:

### Target Platforms
1. **Windows 11 + NVDA (latest) + Firefox / Edge:** Start NVDA (`Ctrl+Alt+N`), verify Speech Viewer (`NVDA+N -> Tools -> Speech Viewer`).
2. **Windows 11 + JAWS + Chrome / Edge:** Start JAWS, verify Virtual PC Cursor navigation (`H` headings, `D` landmarks, `B` buttons, `F` form controls).
3. **macOS Sonoma/Sequoia + VoiceOver (`Cmd+F5`) + Safari:** Verify Web Rotor (`VO+U`) lists Landmarks, Headings, Links, and Form Controls cleanly in both `EN` and `AR`.
4. **iOS (iPhone) + VoiceOver + Mobile Safari:** Single-finger swipe through header, hero, catalog cards, PDP size buttons (`aria-disabled` announcement on sold-out sizes), `NoPhotoFitModal` sliders, wishlist heart toggle, and checkout summary.
5. **Android + TalkBack + Chrome:** Linear swipe + Explore-by-Touch verification on 360dp portrait viewport, verifying zero focus escape behind open drawers/modals and clear touch target spacing.

### Mandatory 7-Step Journey Script (Run Twice: Once in `English`, Once in `العربية`)
1. **Route Announcement & Skip Link:** Load `https://confit-a.vercel.app/`, press `Tab` once to reveal `"Skip to main content"` / `"انتقل إلى المحتوى الرئيسي"`, press `Enter`, confirm focus lands on `<main id="main-content">`, then navigate to `/catalog` and confirm `RouteAnnouncer` speaks the new page title once (`aria-live="polite"`).
2. **Catalog Filtering & RTL Directionality:** Switch language to `العربية`, confirm `<html lang="ar" dir="rtl">`, apply category/size filters, confirm results update without resetting scroll unexpectedly, and confirm all filter buttons and clear chips speak Arabic labels.
3. **PDP Gallery & Sold-Out SKU Guidance:** Open any multi-photo product, step through gallery thumbnails via keyboard arrows/buttons, tab across in-stock and sold-out sizes (`aria-disabled="true"`), confirm sold-out size remains discoverable and announces unavailable status clearly.
4. **Fit Finder Modal Trap, Sliders & Size Handoff:** Activate `"Find my size"` / `"اعرف مقاسي"`, confirm `Escape` closes and restores focus to the trigger button; reopen, adjust Height/Weight range sliders with arrow keys (hearing localized `centimeters` / `سنتيمتر` and `kilograms` / `كجم`), calculate size, apply recommended size, and confirm exact matching in-stock SKU is added to bag.
5. **Wishlist Optimistic Toggle & Persistence:** Toggle heart button on a product card/PDP (`aria-pressed="false" -> "true"`), reload page while signed in, confirm saved state persists across reload without duplicate entries.
6. **Cart, Checkout & Bidi Number Integrity:** Open `/cart` -> `/checkout`, verify SKU codes, order numbers, quantities, and currency totals render cleanly without RTL bidi scrambling (`<bdi>` / `dir="ltr"`), and verify validation messages focus or announce cleanly via `role="alert"`.
7. **Partner Portal CSV Export & Import Feedback:** Sign in as brand manager, open `/brand-dashboard/analytics`, trigger CSV export (confirm Excel opens Arabic titles cleanly via UTF-8 BOM and neutralizes any `=`, `+`, `-`, `@` prefix cells), and upload a multi-row CSV verifying live job status transitions (`queued -> processing -> completed`).
