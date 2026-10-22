# Benchmark dataset

The manifest (`manifest.example.json`, schema in `manifest.schema.json`) is the only
part of the test set that lives in git. **Image bytes are never committed** (see
`.gitignore`): they may be people's photos and third-party garment images, so they
carry consent and licensing obligations that git history must not capture.

## Building a real set

1. Source a **diverse** set with documented provenance and consent: varied body types,
   skin tones, poses, lighting, and garment categories, **including modest wear**
   (abaya, hijab), plus deliberately hard cases (busy patterns, logos, sheer fabric,
   layering).
2. Put the image files under `images/` locally (or an object store); reference them by
   path in a manifest.
3. Fill every `consent_status` with real, documented consent/licensing. The runner
   **refuses a real run** (`--no-dry-run`) while any case lacks `consent_status`.
4. Keep the set fixed and versioned (name it in `dataset`) so runs are comparable.

## Honesty

- No invented ground truth. Scores come from a human rubric (second reviewer / blind
  comparison where practical), not from a fabricated reference image.
- Report the full set; do not cherry-pick favourable cases.
