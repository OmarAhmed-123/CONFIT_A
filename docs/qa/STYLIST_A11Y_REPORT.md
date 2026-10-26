# Wardrobe stylist — accessibility report (P4)

Date: 2026-10-26 · Scope: Wardrobe → *AI Stylist* tab (form, result, Save this
look) and *My Looks* → "Saved wardrobe looks". Built SPA against the real API
with **live** `ibm/granite-4-h-small` answers (no mocks in the browser path).

## Method — what was actually run

| Layer | Tool | Evidence file |
|---|---|---|
| Automated, engine-independent | Playwright (chromium-headless-shell 1243) + axe-core 4.x, WCAG 2.0/2.1/2.2 A+AA tags; **keyboard-only** journey; ARIA snapshots (what AT receives); tab order; live-region text; focused element after result | `docs/qa/stylist_a11y_report.json` |
| Automated, second engine | Same script in **headed Firefox** (Playwright build 1543) under Xvfb | `docs/qa/stylist_orca_report_firefox.json` |
| **Real assistive technology** | **GNOME Orca 48.1** on an AT-SPI2 bus (Xvfb :99, D-Bus session, `org.a11y.Status.IsEnabled=true`), headed Firefox with `MOZ_ACCESSIBILITY_AT_SPI=1`; Orca debug log → every `SPEECH OUTPUT` / `BRAILLE LINE` | `docs/qa/stylist_orca_report.json` (821 lines) |
| Unit | vitest-axe in EN + AR/RTL for `WardrobeStylistPanel` and `SavedWardrobeLooks` | `frontend/src/components/wardrobe/__tests__/` |

Scripts: `frontend/scripts/stylist_a11y_audit.mjs`, `scripts/qa/orca_stylist_session.sh`.

## Results

### axe-core (8 page states: form / result / saved / looks × EN, AR)
**0 violations** in every state, both engines.

### Keyboard & focus (automated, both locales)
* Form: 23 tab stops, all reachable, no traps; result card: Swap-out ×3 → (Upload piece when a category is missing) → Another outfit → Save this look.
* After generation, focus moves to the result heading (`<h3 tabindex=-1>`): EN "Smart Casual Smart Look", AR «لباس سمارت كازوال مع براون لوفرز» (WCAG 2.4.3).
* Live regions after save: EN "Saved to your wardrobe looks (#3). Find it under Looks.", AR «حُفظت ضمن إطلالات خزانتك (رقم 4). ستجدها في تبويب الإطلالات.» (4.1.3).
* `dir=rtl` honoured on the AR Looks tab; provenance badge «من إعداد ibm/granite-4-h-small».

### Orca (real screen reader) — English journey, verbatim excerpts
```
Outfit recommendation landmark
Smart Casual Smart Look heading 3 clickable.
Recommended pieces List with 3 items
Swap out Navy Chinos button.            ← after fix (run 2)
Save this look button grayed.
Saved to your wardrobe looks (#5). Find it under Looks.   ← run 1
Saving…
My Looks button.
```
Also observed: page summary ("Page has 5 landmarks, 4 headings…"), region/
form enter/leave announcements, "Stylist model: ibm/granite-4-h-small · 3 analysed pieces available."

### Defect found by the AT pass and fixed in this branch
* **Identical button names**: three "Swap out" buttons announced as "Swap out
  button." with no garment — a screen-reader user could not tell which piece
  they were removing. Fixed with `aria-label="Swap out {{item}}"` (EN/AR);
  verified with Orca ("Swap out Navy Chinos button.") and in the unit test.

### Design decisions checked against AT
* Save button keeps a constant name ("Save this look"); progress is conveyed by
  `aria-busy`, `disabled` + "grayed", `aria-describedby` → status line, and the
  live region ("Saving…" → "Saved to your wardrobe looks (#n)…"). Orca read all
  three states.
* Fallback vs AI: badge text differs ("Styled by ibm/…" vs rule-based copy) and
  the saved-look badge says "Rule-based (no AI)" — never colour-only.

## Explicitly incomplete
1. **Orca covered the English journey only.** Orca did not follow focus into the
   second browser window used for the Arabic pass, so **AR has no real-AT
   transcript** — AR is covered by axe + ARIA snapshots + live-region capture.
2. No NVDA/JAWS/VoiceOver/TalkBack session (no Windows/macOS/mobile in this environment).
3. Orca + espeak-ng Arabic pronunciation quality not assessed.
4. Live-region ordering in the Orca log ("Saved…" before "Saving…") reflects
   event batching in the log, not UI order; a human SR user test should confirm
   the perceived order.
5. The rest of the wardrobe page (carousel "Item 1 of 5" announcements etc.) is
   pre-existing and out of scope; noted because it is chatty on page load.

## Verdict
Automated: **PASS** (0 violations, keyboard-complete, focus + live regions
correct, EN/AR). Real AT: **PARTIALLY VERIFIED** (Orca, EN, Firefox) with one
defect found and fixed. A human screen-reader review (incl. Arabic) remains outstanding.
