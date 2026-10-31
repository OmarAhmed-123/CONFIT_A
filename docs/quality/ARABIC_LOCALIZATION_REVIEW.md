# Arabic Localization Review — 2026-10-29

**Status: engineering pre-review PREPARED; native-speaker sign-off NOT OBTAINED.** Reviewer sheet: `docs/qa/ARABIC_REVIEW_SHEET_STYLIST.md`. Nobody is named as reviewer here.

## 1. Language policy (determined from the bundle, not assumed)

* `frontend/src/i18n/ar.json` is written in **Modern Standard Arabic (فصحى)**. Automated scan of 3 226 strings for Egyptian-colloquial markers (ده/دي/مش/عايز/كده/ليه/فين/علشان …) found **2 genuine dialect strings**, both in the brand back-office namespace: `brand_orders.totals_scope` ("الإجماليات بتغطي … مش الصفحة دي بس") and `brand_orders.load_failed` ("مش قادر أحمّل …"). One further hit (`legal.gdpr_transfers_body`) is a false positive.
* **Policy recorded**: *MSA for all product and legal copy; no dialect.* The two colloquial strings are a defect (LOC-1), proposed fix in §4.
* Prompting: the stylist prompt asks Granite for Arabic output in the user's language; the live outputs (§3) are MSA.

## 2. Bundle parity and mechanics (verified by script, exit 0)

| Check | Result |
|---|---|
| Keys EN / AR | 3 215 / 3 226 — **0 missing in AR**, 11 extra AR-only keys (harmless; `npm run i18n:check` passes) |
| AR values containing no Arabic letters | 1 (`checkout.email_placeholder` = an e-mail example — acceptable) |
| Identical EN==AR strings | 0 |
| `document.documentElement.dir` in AR session | `rtl` (browser E2E, both desktop and mobile) |
| Horizontal overflow at 390 px (AR) | none (`docs/qa/evidence/review_20261029/keyboard_and_viewport_findings.json`) |

## 3. UI findings from screenshots (`docs/qa/evidence/review_20261029/ar_*`)

| ID | Finding | Severity | Verified / Proposed |
|---|---|---|---|
| LOC-2 | Closet category filter chips render English (`All · Outerwear · Tops · Bottoms · Footwear`) in the AR session (`ar_mobile_closet.png`) | Medium | Verified; fix proposed: map taxonomy category through `wardrobe.category_*` keys (already exist) |
| LOC-3 | Garment meta line shows taxonomy family + category in English ("Green · Bottoms", "Black · Footwear") | Medium | Verified; colour families need an AR label map (only `Unknown` is localised today via `wardrobe.color_unknown`) |
| LOC-4 | Image placeholder text "image unavailable" English in AR | Low | Verified; add key |
| LOC-5 | Mixed-direction strings such as "Rule-based match — not AI" badge are localised ("مطابقة قائمة على القواعد — ليست ذكاءً اصطناعياً") ✔ | — | Verified OK |
| LOC-6 | Numerals: Western digits used throughout AR UI (1/5, 1/6) — consistent, acceptable under MSA policy; decide and record | Info | Policy decision pending |

## 4. Live Granite Arabic output (3 AR scenarios, `wardrobe_stylist_eval_live_20261028.json`)

Observed quality: fluent MSA, fashion vocabulary correct (كحلي، كاكي، كلاتش، شال). Issues a reviewer should confirm:

| ID | Example | Issue |
|---|---|---|
| LOC-7 | "احملي قبعة شمسية" vs "اختر حذاء كعب فضي" | **Grammatical gender inconsistency** across responses (feminine vs masculine imperative) — prompt does not state addressee gender; propose a neutral form ("يُنصح بـ…") in the prompt guidance |
| LOC-8 | "في قاعة مغطى" | agreement error (should be مغطاة) |
| LOC-9 | "بدون التزامن مع الطقس", "يناسب الرسمي" | calque / unnatural phrasing — typical LLM Arabic; acceptable or not is a reviewer call |
| LOC-10 | "يتجنب اللون الأسود المستبعد" (S13) | constraint echo is correct and honest ✔ |

## 5. Proposed fixes (not applied in this pass unless noted)

1. LOC-1: rewrite the two `brand_orders` strings in MSA (`الإجماليات تغطي جميع الأسطر المطابقة ({{count}})، وليس هذه الصفحة فقط.` / `تعذّر تحميل أسطر الطلبات.`) — trivial, awaiting the reviewer to avoid piecemeal edits.
2. LOC-2/3/4: localise taxonomy labels in `WardrobeView`/`WardrobeStylistPanel` through existing keys + a new `wardrobe.color_family.*` map. Estimated ½ day incl. tests. (`Unknown` done this pass as part of Phase 11-A.)
3. LOC-7: add "use gender-neutral imperative forms" to the Arabic prompt instructions and re-run the 3 AR scenarios live.

## 6. Sign-off

| Role | Status |
|---|---|
| Native Arabic speaker (fashion domain) | **NOT REVIEWED** |
| Engineering parity / RTL mechanics | VERIFIED 2026-10-29 |
