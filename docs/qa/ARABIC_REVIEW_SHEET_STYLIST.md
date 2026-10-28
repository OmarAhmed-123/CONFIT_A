# Arabic review sheet — wardrobe stylist (P4 l10n)

Sheet: [`ARABIC_REVIEW_SHEET_STYLIST.csv`](./ARABIC_REVIEW_SHEET_STYLIST.csv) —
81 strings under `wardrobe_stylist.*` (EN source · current AR · UI context ·
register · reviewer feedback · approved). Open in Excel/Sheets (UTF-8 BOM).

## Status — honest

* **Native-speaker review: OUTSTANDING.** The Arabic strings were authored by
  the implementer in Modern Standard Arabic and checked mechanically only
  (placeholder parity test `i18nParity.test.tsx`, RTL axe pass, screenshots
  `docs/qa/watsonx_stylist_result_ar.png`). Nobody has signed the `approved` column.
* Arabic plural forms for `saved_looks_dropped_*` use i18next's CLDR
  categories (`zero/one/two/few/many/other`); the `one`/`two` variants keep
  `{{count}}` to satisfy the placeholder-parity gate — reviewer may prefer
  dropping the numeral in prose; if so the parity test must be adjusted
  deliberately, not bypassed.
* Known gaps to put in front of the reviewer first:
  1. Garment titles/categories inside a look come from the user's data or the
     English taxonomy (`Tops`, `Footwear`); the AR UI shows them untranslated.
  2. Model-produced reasons/summaries in AR depend on the model honouring the
     `language=ar` instruction (`STYLIST_SYSTEM_PROMPT`); quality is unreviewed.
  3. `source_model` reads «من إعداد {{model}}» with a Latin model id inside an
     RTL sentence — check bidi rendering on device.

## How to run the review

1. Reviewer fills `reviewer_feedback` and `approved` (`yes`/`no`) per row.
2. Apply edits in `frontend/src/i18n/ar.json` (same keys), run
   `npx vitest run src/i18n src/components/wardrobe`.
3. Record the reviewer's name/date here and flip the status line above.


## Update 2026-10-27

Strings added (need the same native review as the rest — **not yet reviewed**):
`wardrobe_stylist.excluded_colors` = «ألوان يجب تجنّبها», `…_placeholder` =
«أسود، أحمر», `…_hint` = «تُستبعد القطع بهذه الألوان من الاقتراح نهائيًا، وليس مجرد تقليل أولويتها.».
Server-side Arabic text added: limitation «تم استبعاد N قطعة لأنها بلون طلبتَ تجنّبه (…)» and
«لم نتعرّف على «…» كلون، لذا لم يُطبَّق استبعاد تلقائي له.» — note the colour family names
inside the parentheses are the taxonomy's English family labels (e.g. `Black`); localising
family names is a follow-up. The taxonomy now understands Arabic colour words
(أسود/أبيض/كحلي/…), which makes preferences and exclusions typed in Arabic effective for
the first time. Native-speaker review: **BLOCKED — NOT VERIFIED** (no reviewer available
in this environment); owner: product/localisation.


## Update 2026-10-28 — live-model Arabic samples + new server strings

Native-speaker review status: **still BLOCKED — NOT VERIFIED** (no native Arabic reviewer available
in this environment). Everything below is an assistant observation, queued for the reviewer.

### Live Granite output (ibm/granite-4-h-small), raw samples for review
Source files: `docs/qa/eval/wardrobe_stylist_eval_live_20261027.json`, `…_20261028.json` (scenarios S12–S14).

| Run | Scenario | Sample (verbatim) | Assistant observation | Reviewer decision |
|---|---|---|---|---|
| 10-27 | S14 summary | «…لحفل زفاف في قاعة مغطى باللون الأسود.» | Grammatically odd — "hall covered in black" appears to be a mangled rendering of the excluded colour. | _pending_ |
| 10-27 | S13 assumption | «المقابلة تتطلب ملابس رسمية وليس بدون تيشيرت أو بدلة رسمية.» | Incoherent double negation. | _pending_ |
| 10-28 | S13 summary | «القميص الأبيض مع البنطلون الكحلي يشكلان مجموعة عمل رسمية مناسبة لمقابلة عمل صباحية في الخريف، بينما الحذاء البني يضيف لمسة دافئة دون انتهاك الحظر على الأسود.» | Reads naturally; «انتهاك الحظر» is a slightly legalistic register for a stylist. | _pending_ |
| 10-28 | S14 summary | «فستان سهرة كحلي يناسب الحفل الرسمي في الليلة الزفاف…» | «في الليلة الزفاف» is ungrammatical (definite article on both words of an iḍāfa); should be «في ليلة الزفاف». Model also wrote «الملابس الشخصية» for "wardrobe" instead of «الخزانة» used elsewhere — terminology inconsistency. | _pending_ |
| 10-28 | S12 | full response | Clean; consistent with 10-27 run (regression sample). | _pending_ |

### New server-side Arabic strings (D10/D11/D12 fixes, `wardrobe_stylist_service.py::_FALLBACK_TEXT["ar"]`)
`unsuitable_summary`, `partial_summary`, `filtered_summary`, `incomplete_word`/`complete_word`,
`neutral_reason`, `generic_reason`, `unfilled`, `role_collision`; UI badges `wardrobe_stylist.fit_partial`
= «مطابقة جزئية», `wardrobe_stylist.fit_unsuitable` = «لا توجد إطلالة مناسبة — تُعرض أقرب القطع».
Known limitation carried over: occasion values inside these strings are the request's English enum
(e.g. «موسومة لمناسبة Active») — localising occasion names is a follow-up.
