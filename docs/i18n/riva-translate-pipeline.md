# EN → AR UI translation with the dedicated NVIDIA credential

**Date:** 2026-10-17 · **Branch:** `feat/uiux-individual-grid-audit` (PR #354)
**Credential:** `NVIDIA_API_KEY_RIVA_TRANSLATE` · **Model:** `nvidia/riva-translate-4b-instruct-v2`
**Tool:** `frontend/scripts/translate_ui_strings.py`

## 1. Scope

126 hard-coded English strings across seven screens were extracted into
`en.json` / `ar.json`:

| File | Strings | Audience |
|---|---|---|
| `views/consumer/WardrobeView.tsx` | 29 | shopper |
| `components/tryon/VirtualTryOnModal.tsx` | 37 | shopper |
| `components/tryon/NoPhotoFitModal.tsx` | 15 | shopper |
| `components/wardrobe/DuplicateAlertModal.tsx` | 7 | shopper |
| `views/b2b/BrandInventoryView.tsx` | 17 | brand operator |
| `views/b2b/BrandAnalyticsView.tsx` | 12 | brand operator |
| `views/b2b/BrandPlacementsView.tsx` | 22 | brand operator |

## 2. The model ignores the system turn — measured

`backend/app/providers/nvidia/registry.py` (`ModelRole.TRANSLATION`) already
records this. It was re-measured here before any string was shipped:

| Prompt shape | Result |
|---|---|
| Instruction in the **system** turn | 6 of 9 short strings returned in the wrong language — French (`Eliminer`), Norwegian (`Arbeidsbekledning`), Ukrainian, Czech |
| Instruction in the **user** turn | 12 of 12 clean Arabic |

**Therefore the instruction lives in the user turn.** It is also kept to one
sentence: with a multi-sentence rule block, the model translated the *rules*
and returned them as the answer (`"قواعد: احتفظ بكل رمز مكتوب ك…"` in place of
the string). Guard `G8` rejects that class of output.

This is consistent with the registry's existing verdict — *"Fluent but
instruction-blind … Better than no translation when super is down — never the
first choice."* The translation role's primary remains
`nvidia/nemotron-3-super-120b-a12b`; riva is `FAILOVER_2`.

## 3. Verification

Every string is put through mechanical guards, then a human review pass:

| Guard | Catches |
|---|---|
| `G1` | output contains no Arabic at all |
| `G2` | Latin leaked beyond a curated allow-list (formats, table/field identifiers, brand names) |
| `G3` | an `{{interpolation}}` token from the source was dropped |
| `G5` | output identical to the English source |
| `G6` | long source collapsed into a fragment (truncation) |
| `G8` | the model echoed our instructions instead of translating |

`G1`–`G8` passed for **120 of 126** strings after resampling. The 6 remaining
"failures" are the two acronyms deliberately kept (`BOPIS`, later translated;
see §5) and `{{placeholder}}` names, which were a guard bug, not a
translation bug.

## 4. What the guards do NOT catch — 67 of 126 needed a reviewer correction

**53% of the drafts were wrong in ways the guards cannot see.** These are real
examples from this run:

| English | riva first draft | Literal meaning of the draft | Shipped Arabic |
|---|---|---|---|
| Unlocks +N New Outfits | `أزِل +N …` | **"Remove +N …"** | `يُتيح لك +N …` |
| Conversion Funnel | `…القالب` | "the template" | `قمع التحويل` |
| Trending Placements | `…التقنيات المتطورة` | "cutting-edge technology" | `… والأكثر رواجًا` |
| failed orders | `المفلسة` | "bankrupt" | `الفاشلة` |
| styling what you own | `تزيين` | "decorating" | `تنسيق` |
| Size (garment) | `الحجم` | "volume/bulk" | `المقاس` |
| return-marked line | `العلامات المرسومة` | "drawn marks" | `بنود … كمرتجع` |
| Worn | `مستخدم` | "second-hand" | `مرات الارتداء` |
| Add Anyway | `…الملف` | "the **file**" | `تابع الإضافة` |
| Dressing Canvas | `خزانة قماش` | "fabric cupboard" | `لوحة الإلباس` |
| Play Layer Sequence | `تسلسل طبقات اللعب` | "sequence of play layers" | `تشغيل تسلسل الطبقات` |
| not a drape fit | `تناسب الدrape` | untranslated fragment | `وليس قياس انسيابية القماش` |

**The most dangerous single case** was not a nonsense word but an inverted
epistemic claim. The B2B placements disclaimer says *"Daily reset and event
deduplication are **not established** by this screen."* riva returned Arabic
asserting the counters **are not** reset — turning "we have not verified this"
into "this does not happen". In a codebase whose B2B screens exist to be
honest about what is and is not proven, that inversion would have been a
material misstatement. The reviewed Arabic restores the hedge.

**Conclusion: this model is a first-draft engine, not a translation oracle.**
It is usable only with a mandatory reviewer pass, and the reviewer must be
able to read Arabic *and* know the domain vocabulary.

## 5. Vocabulary decisions

Consistent with the terms already in `ar.json`:

| English | Arabic |
|---|---|
| Try-On | القياس الافتراضي |
| Stylist | منسق المظهر |
| Outfit / Look | إطلالة |
| Wardrobe | الخزانة |
| Placements | المواضع الإعلانية |
| garment size | المقاس |
| (Real) — measured, not mocked | (فعلي) |

Two acronyms were **translated** rather than added to `NON_TRANSLATABLE`:
`b2b.inv_bopis_title` → `الاستلام من المتجر (BOPIS)` and
`b2b.placements_roas` → `العائد على الإنفاق الإعلاني:`. The `i18nParity`
test's allow-list is empty by design (`ar.json is NOT a copy of en.json`);
widening it for a string that has a standard Arabic term would weaken a guard
the project relies on.

## 6. Result

* `tsc --noEmit` — 0 errors
* `i18n:check` — pass
* `vitest` — 135 files / 1597 tests, 0 failures
* `vite build` — clean
* Browser probe, `localStorage.confit_lang = 'ar'`:
  * `/wardrobe` → `dir=rtl`, 2173 Arabic characters, **0** unresolved i18n keys
  * `/fit` → `dir=rtl`, 1893 Arabic characters, **0** unresolved i18n keys
  * `/brand/*` → **not visually verified**; the preview ran without the
    backend, so those routes never rendered past the auth gate. They are
    covered by `tsc` + `i18n:check` + the test suite only.
