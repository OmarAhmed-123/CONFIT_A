# archtest_inputs — PROVENANCE (runtime-unknown architecture test inputs)

Generated: 2026-09-15, turn: Dynamic Real-User Multi-Garment VTON phase,
architecture tests AT-01..AT-19.

## Status of these files

These images are **runtime inputs for architecture tests only**. They are:

- **NOT** registered in `evaluation/fixtures/person_manifest.json`
  (p001..p030) or `evaluation/fixtures/garment_manifest.json` (g001..g024);
- **NOT** part of the benchmark, calibration, training, or regression corpora;
- **NOT** used by any production code path (production resolves garments
  from the catalog DB and persons from the user request — see
  `backend/app/services/tryon_service.py`);
- named `person_rt{1..4}` / `garment_rt{1..4}` precisely so they cannot be
  confused with benchmark fixture IDs (`p0xx` / `g0xx`), and so the §21
  fixture-ID code scan stays meaningful.

## Persons (4) — generated 2026-09-15, AI image generation (this session)

| file | description (generation prompt intent) |
|---|---|
| person_rt1.jpg | male, early 20s, short light-brown hair, clean shaven; white tank + gray joggers; studio, 3:4 |
| person_rt2.jpg | female, mid 20s, straight black hair to shoulders; white tank + dark gray joggers; studio, 3:4 |
| person_rt3.jpg | male, early 30s, short dark hair, full dark beard; white tank + gray joggers; studio, 3:4 |
| person_rt4.jpg | female, late 20s, voluminous dark curly hair; white tank + dark gray joggers; studio, 3:4 |

All four are visually distinct individuals, never seen in any prior
benchmark/calibration run (the p0xx cohort is a different set of people).

## Garments (4) — generated 2026-09-15, AI image generation (this session)

| file | description | engine slot |
|---|---|---|
| garment_rt1.jpg | plain teal short-sleeve crewneck tee, flat-lay, white bg | upper_inner |
| garment_rt2.jpg | plain olive chinos trousers, flat-lay, white bg | lower |
| garment_rt3.jpg | plain mustard short-sleeve crewneck tee, flat-lay, white bg | upper_inner |
| garment_rt4.jpg | plain burgundy **long-sleeve** tee, flat-lay, **vertical sleeves**, white bg, landscape — the Phase 0.5 sleeve-transfer geometry family, used to test the generic sleeve gate (AT-16b/AT-19) on an UNKNOWN garment | upper_inner |

In tests these garments enter the system the same way a real catalog garment
does: a NEW `products` row is inserted into the test DB with the flat-lay as
`thumbnail_url` (data URL); the client submits only the `product_id`.

## Unknownness claim (evidence rule)

- VERIFIED by construction: files created in this session after all Phase
  0.5/1 fixture generation; filenames carry the `rt` (runtime) prefix that
  appears in no manifest; `evaluation/fixtures/*.json` contain no `rt`
  entries (checked at suite runtime by the §21 scan, which must stay ZERO).
- If these images are ever promoted to fixtures, they MUST be regenerated or
  the promotion documented — otherwise future "unknown input" tests using
  them would silently become known-input tests.
