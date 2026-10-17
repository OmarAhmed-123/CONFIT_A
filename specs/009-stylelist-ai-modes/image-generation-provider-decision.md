# Outfit-only image generation: provider decision (PENDING APPROVAL)

Status: **no provider approved. No generation calls made. No customer photo sent to any new service.**

## What the repository already has (verified in code)
* **Vision analysis:** NVIDIA `google/diffusiongemma-26b-a4b-it`, with `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` as failover (`GARMENT_VISION`). Live-verified on two photos (see verification.md §10.14). This is an image-INPUT capability only.
* **Stylist answer model:** NVIDIA `nvidia/nemotron-3-super-120b-a12b` (text).
* **Image generation: none authorised for stylist visuals.** The only generative path is the virtual try-on worker on Modal (`fashn-vton`, `MODEL_REGISTRY.json`). It produces a person wearing the garments, which conflicts with the mannequin-free requirement. Try-On handoff is blocked on workstream 008 (tasks.md T023 / T-STY-09).

## Requirements a provider must meet
* Outfit-only output: no person, face, body, mannequin, silhouette, or body parts.
* Built from the verified selected outfit (item categories, colours, style), not a generic prompt.
* Clearly labelled as an illustrative concept, never as a photo of an SKU.
* No fabricated logos or branding.
* Data: customer photos must not be sent unless the user consents and the approved privacy controls apply. Preferably, only the verified text description is sent, not the photos.

## Candidate evaluation (NOT yet verified against official documentation)
Secondary aggregator pages reported text-to-image prices roughly between $0.003 and $0.06 per image (e.g. FLUX.2 pro ~$0.03–0.055 per image; some models from ~$0.005). These are third-party figures, not official price lists, so they must be checked on the provider's own pricing page before any approval.

Still to be checked before approval, per candidate:
1. Official docs: supported modalities, whether image-to-image editing is offered, and output size.
2. Price per image and monthly cap.
3. Auth: a new environment variable name, stored in the approved secret manager. No new secret is created without approval.
4. Retention and training-use terms (critical if photos are ever sent).
5. Rate limits, typical latency, timeout, and retry policy.
6. Reliability at producing people-free outfit boards (needs a test set, measured live).

## Storage and failure policy (for when approved)
* Generated images are stored as files with a content hash, never as base64 in stylist database rows.
* Each generated image is labelled "Illustrative concept" and stored with its source outfit ID.
* On provider failure, timeout, or safety rejection: show the honest status, keep the catalogue visual fallback, and never substitute an unlabelled image.

## Interim visuals (in force now)
Catalogue product photographs or existing authorised stock images, labelled as "Catalogue/stock imagery: not generated from your garments." Only when a real image exists for the item.

## Decision needed from the user
1. Approve an image-generation provider? If yes, name it.
2. Approve the per-image budget and monthly cap.
3. Approve whether customer photos may be sent (recommended: no; send the verified text description only).
