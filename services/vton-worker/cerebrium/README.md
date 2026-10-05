# CONFIT VTON WORKER — Cerebrium shell (feature 03, multi-garment)

Third GPU platform candidate for the `fashn_v15` multi-garment worker, after
Modal (running, grandfathered segfee app; no payment method for new apps) and
Baseten (blocked: no payment method on the workspace AND custom base images
are org-gated). This directory holds **no logic** — it is a pure re-host of the
exact same CI-built image the Baseten path uses:

```
ghcr.io/omarahmed-123/confit-vton-worker-baseton:main     (public)
```

built by `.github/workflows/build-vton-baseten-image.yml` from
`services/vton-worker/baseten/Dockerfile` (CUDA 12.4 + pip deps + vendored
pristine fashn-vton-1.5 + CONFIT engine/server layers + ~2.2GB weights baked
at build time). `./Dockerfile` here is a one-line `FROM` that base image —
EXPOSE/CMD/ENV (incl. `PYTHONPATH` and `VTON_WEIGHTS_DIR`) are all inherited —
so the deployed container is bit-identical to the Baseten deployment. One
artifact, multiple deployment targets, zero drift.

Why a shim Dockerfile instead of `docker_base_image_url` + `entrypoint`?
Cerebrium CLI 2.9.0 rejects entrypoint-only custom-runtime configs with
"main.py not found"; `dockerfile_path` is the validated route (the config
packages and passes the CLI's client-side validation — confirmed 2026-10-04).

## Why Cerebrium fits our contract (where Baseten's standard path didn't)

| Requirement | Cerebrium support |
| --- | --- |
| Arbitrary routes `/health` `/readiness` `/process` | ✅ custom runtime exposes every route at `/v4/{project}/{app}/<path>` |
| Custom Docker image (weights baked, hermetic) | ✅ `dockerfile_path` shim FROM the public GHCR image (anonymous pull verified) |
| Scale to zero (surgical GPU spend) | ✅ `min_replicas = 0`, per-second billing |
| Cheap 24GB GPU | ✅ NVIDIA L4 (`ADA_L4`, Hobby+ plan, ~$0.000222/s) |
| Defense-in-depth auth | ✅ `disable_auth = false` (Cerebrium JWT) **and** worker `X-VTON-Admin` |

## Deploy (one command, once unblocked)

```bash
export CEREBRIUM_SERVICE_ACCOUNT_TOKEN=<service-account-token>
cerebrium project set <project-id>          # p-b99cd366 as of 2026-10-04
cd services/vton-worker/cerebrium
cerebrium deploy --config-file cerebrium.toml
```

**Status 2026-10-04 — BLOCKED at the credential level, deploy not yet run.**
The vault's Cerebrium key authenticates (valid JWT, project `p-b99cd366`,
expiry 2036) but its identity-based policy **explicitly denies every action
needed to deploy**: `apps list`, `apps get`, `apps create` (the deploy's first
step), `projects list`, `secrets list`. The config itself is validated: the CLI
loads the bundle, builds the zip, and reaches the app-create call before the
403 — so unblocking the key unblocks the deploy with zero further changes. To unblock, in the Cerebrium dashboard:

1. **API Keys page → Service Accounts** → open the service account behind the
   key and grant it deploy access to the project (or create a fresh service
   account with full project permissions and put its token in the vault as
   `CEREBRIUM_API_KEY`).
2. **Secrets tab** → add project secret `VTON_WORKER_ADMIN_TOKEN` (same value
   as the Baseten secret `confit_worker_admin_token`) so the worker's
   `X-VTON-Admin` layer works.
3. Confirm a payment method / plan that allows `ADA_L4` (Hobby+); the deny
   message may also be plan-related.

## After deploy: Vercel cutover (config-only, no code changes)

The API service derives worker URLs from `VTON_WORKER_URL` (see
`TryOnService._derive_worker_urls`), so cutover is env-var only:

```
VTON_WORKER_URL   = https://api.cerebrium.ai/v4/p-b99cd366/confit-vton-worker
VTON_WORKER_GATEWAY_AUTHORIZATION = Bearer <cerebrium-inference-token>
VTON_ENGINE       = fashn_v15        (multi-garment one-call path)
VTON_WORKER_HEALTH_TIMEOUT_SECONDS >= 60  (cold start: weights load ~1-2 min)
```

The `X-VTON-Admin` header layer stays exactly as-is (worker enforces it behind
Cerebrium's own JWT gate).

## Cost guardrails (user rule: never burn the GPU budget)

- `min_replicas = 0`, `max_replicas = 1`, `replica_concurrency = 1` — one
  container, alive only for real work + 60s cooldown.
- L4 ≈ $0.000222/s ⇒ a 60s render ≈ $0.014; a cold start (~2 min load) ≈ $0.03.
- The public `/health` VTON status line on the API is passive by design — it
  can never be the reason a billed GPU container exists.
