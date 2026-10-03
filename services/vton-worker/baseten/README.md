# CONFIT VTON Worker — Baseten deployment (feature 03, multi-garment)

The `fashn_v15` multi-garment engine deployed as a **Baseten custom Docker
container** (no-build mode). The HTTP contract is byte-identical to the Modal
deployment because both shells delegate to the same
[`server_core.py`](../server_core.py) — this is the A/B comparison target
requested by the project owner on 2026-10-03 (production wiring on Baseten,
Modal `confit-vton-worker-segfee` kept running for comparison).

## Pieces

| File | Role |
|---|---|
| `../server_core.py` | Shared HTTP layer (validation, SSRF guard, auth, handlers). Single source of truth for both shells. |
| `../baseten_server.py` | Baseten shell: loads the engine at boot, serves `server_core.create_app()` via uvicorn. |
| `Dockerfile` | Self-contained image: CUDA 12.4 runtime + deps + vendored pristine upstream + weights (public HF, baked at build time). No secrets inside. |
| `config.yaml` | Truss config: `no_build` + L4 24GB + scale-to-zero, routes `/sync/*` 1:1 to our routes. |
| `.github/workflows/build-vton-baseten-image.yml` | Builds the image on a GH runner (dev machines cannot hold ~10GB CUDA images) and pushes to GHCR. |

## URL shape (why the backend needs no code change)

Baseten no-build routing maps 1:1:

```
https://model-<id>.api.baseten.co/environments/production/sync/health
https://model-<id>.api.baseten.co/environments/production/sync/readiness
https://model-<id>.api.baseten.co/environments/production/sync/process
```

`TryOnService._derive_worker_urls` derives `/health` `/readiness` `/process`
from `VTON_WORKER_URL=https://model-<id>.api.baseten.co/environments/production/sync`,
so the cutover is env-only.

Auth is two-layered: Baseten's gateway requires `Authorization: Api-Key <key>`
on every route (the backend sends it from
`VTON_WORKER_GATEWAY_AUTHORIZATION`), and the worker still enforces
`X-VTON-Admin` (rotated token, injected as the Baseten secret
`confit_worker_admin_token`, never baked into the image).

## Deploy runbook

```bash
# 1. Build the image (or let the workflow do it on push to main)
#    Actions: "build vton baseten image" — produces
#    ghcr.io/omarahmed-123/confit-vton-worker-baseten:main + :sha-<sha>

# 2. Create the secret ONCE on Baseten (org-level). A Baseten secret is a
#    name -> single value, mounted at /secrets/confit_worker_admin_token with
#    the value as the file content (server_core._expected_admin_token reads
#    that flat file). Create it via the UI (Settings -> Secrets) or the API:
#    POST /v1/secrets {"name": "confit_worker_admin_token", "value": <token>}
#    NOTE: this call needs an API key of type WORKSPACE_MANAGE_ALL — a
#    WORKSPACE_MANAGE_API_KEYS key gets 403 on /v1/secrets.

# 3. Deploy (no GPU time is spent: Baseten copies the image registry-to-registry)
#    NOTE: custom base images (docker_server / no_build) must be enabled for
#    the organization — otherwise truss push fails with
#    "Custom base images not supported for your organization".
truss push services/vton-worker/baseten/   # config.yaml points at the GHCR image

# 4. Verify (this DOES spend GPU minutes — surgical, one pass)
#    Readiness first (no GPU): expect 200 {"ready": true, ...} once warm
curl -H "Authorization: Api-Key $BASETEN_API_KEY" \
     https://model-<id>.api.baseten.co/environments/production/sync/readiness
curl -H "Authorization: Api-Key $BASETEN_API_KEY" \
     https://model-<id>.api.baseten.co/environments/production/sync/health
# expect: model_loaded=true, engine=fashn_v15, multigarment=true, device=L4

# 5. Cutover (Vercel env):
#    VTON_WORKER_URL=https://model-<id>.api.baseten.co/environments/production/sync
#    VTON_WORKER_HEALTH_URL=.../sync/health        (explicit; derivation also works)
#    VTON_WORKER_READINESS_URL=.../sync/readiness
#    VTON_WORKER_PROCESS_URL=.../sync/process
#    VTON_WORKER_GATEWAY_AUTHORIZATION="Api-Key <BASETEN_API_KEY>"
#    VTON_WORKER_ADMIN_TOKEN=<rotated admin token>
#    VTON_ENGINE=fashn_v15
```

## Cost model (honest)

- L4 24GB ≈ **$0.01414/min** ($0.85/h), billed per minute, **scale-to-zero**
  (0 replicas when idle — no burn without jobs).
- Cold start: container start + model load from the baked-in weights
  (no network fetch; HF_HUB_OFFLINE=1). Expect tens of seconds, once per
  scale-up — same trade the Modal deployment makes.
- Public-health reads never spin this worker (backend /health is passive since
  2026-10-03); only real try-on jobs and explicit admin checks hit the GPU.

## Licence honesty (unchanged)

Upstream pipeline/DWPose/YOLOX Apache-2.0; `fashn-human-parser` NVIDIA
SegFormer **non-commercial** (owner-approved for early stage, licensed swap
planned before commercial scale via `engine.FashnV15MultiGarmentEngine(parser_impl=…)`).
