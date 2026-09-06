# VTON Production End-to-End Proof — 6 September 2026

Closes the last open operational item of the 2026-09-05 audit (VTON-01):
*"the team must supply a real inference output, a job log and a verifiable
measure"*.

## What was run

A **real asynchronous VTON job against the production deployment**
(`confit-a.vercel.app`) using a **synthetic, privacy-safe person image**
(AI-generated studio model — no real person's photo was used):

| Step | Detail |
|---|---|
| Auth | Consumer account login (post-rotation credentials), httpOnly cookie + CSRF double-submit |
| Input image | `VTON_PROOF_person_input_20260906.jpg` — synthetic man, white t-shirt, gray trousers, gray studio background (896×1200) |
| Garment | Product id 1 — *Tailored Italian Wool Double-Breasted Blazer* (navy windowpane) |
| Endpoint | `POST /api/v1/tryon/jobs` → `202 Accepted` |
| Engine | Production GPU worker (`fashn_vton_segfee` fork per health registry) |
| Result | `status: completed` in ~40 s; one-shot temporary delivery download (token, TTL 900 s) |

## Verifiable measures (from the job response, not from the UI)

```json
"metrics": {
  "PASS": true,
  "metric_pixel_change": 11.1313,
  "metric_color_shift": 0.076373,
  "metric_image_stddev": 42.66,
  "garments_requested": 1,
  "verification": {
    "all_layers_verified": true,
    "layers_requested": 1,
    "layers_failed": 0,
    "failed_layers": []
  }
}
```

`metric_pixel_change = 11.13` is a measured image-space delta — orders of
magnitude above a no-op overlay (the engine's own `verify.PASS` gate that
PR #59 made a hard requirement: a layer whose garment was not materially
applied now fails with `VTON_LAYER_NOT_APPLIED` instead of "succeeding").

## Visual evidence (both committed in this folder)

- `VTON_PROOF_person_input_20260906.jpg` — the submitted person (no blazer).
- `VTON_PROOF_blazer_output_20260906.jpg` — the production output: the **same
  person/pose/background** now wearing the navy windowpane double-breasted
  blazer over a white shirt with a pocket square — real garment drape, shade
  and fit deformation rendered by GPU inference.

Known engine-quality artifact: minor hand deformation near the pockets
(typical diffusion edge case) — noted honestly; it is a quality-tuning
concern of the engine, not a fake/pipeline defect.

## Audit traceability

- Audit VTON-01 → **CLOSED (evidence attached)**: real inference output +
  job record + verifiable metrics, produced on production.
- PR #59 hard gate (`VTON_LAYER_NOT_APPLIED`, `verify.PASS is True`) is the
  standing invariant that keeps every future render honest.
- Privacy: job submitted with `consent_retain_photo=false`; temporary
  delivery auto-expires (24h anonymous expiry policy).
