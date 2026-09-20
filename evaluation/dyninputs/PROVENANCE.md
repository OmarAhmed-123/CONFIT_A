# Dynamic Validation Input Provenance (local + global cohorts)

Generated 2026-09-15 exclusively for the LOCAL/GLOBAL DYNAMIC VALIDATION runs
(docs/vton/LOCAL_DYNAMIC_VALIDATION_REPORT.md, GLOBAL_DYNAMIC_VALIDATION_REPORT.md).

## Unknownness claim
None of these images appears in any fixture manifest, benchmark, calibration,
training, or regression corpus of this repository. They were generated for this
validation phase and used only here. (Same standard as ../archtest_inputs/PROVENANCE.md.)

## Files
- local/person_local_hijab.jpg — Egyptian woman, white hijab, modest tunic; full-body studio.
- local/garment_local_arabic_tee.jpg — olive long-sleeve tee, white Arabic text "القاهرة".
- local/garment_local_dress.jpg — charcoal one-piece long-sleeve dress.
- global/person_global_a.jpg — athletic man, dark skin; full-body studio.
- global/person_global_b.jpg — woman, medium build, freckles; difficult lighting (dim tungsten room).
- global/garment_global_text_tee.jpg — white tee, black English text "CONFIT".
- global/garment_global_logo_blazer.jpg — navy blazer, generic geometric triangle logo (no brand marks).

Outputs: evaluation/results/outputs/dyn_*.png (gitignored workspace artifacts;
hashes recorded in evaluation/results/dynamic_validation_evidence.json).
