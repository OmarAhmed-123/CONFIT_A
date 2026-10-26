# Granite Vision availability investigation (P2)

Date: 2026-10-26 · Method: live calls with the operator's IBM Cloud API key
(IAM bearer → watsonx.ai REST), IBM public documentation. No SDK, no guesswork.

## Question

The IBM tutorial uses `ibm/granite-vision-3-2-2b` for garment analysis. In the
first integration pass every call returned `404 model_not_supported`, so the
vision step runs on `meta-llama/llama-4-maverick-17b-128e-instruct-fp8` with
disclosed provenance. Is Granite Vision **retired**, a **permission/plan**
problem, a **region** problem, or a **code defect**? And can it be integrated?

## What was checked (LIVE)

| # | Probe | Result |
|---|---|---|
| 1 | `GET {region}/ml/v1/foundation_model_specs?version=2024-10-10&limit=200` for **eu-de, us-south, eu-gb, jp-tok, au-syd, ca-tor** (no filters — the `filters=` form returns HTTP 400) | **No `ibm/granite-vision-*` entry in any region.** `image_chat`-capable models served multitenant: `meta-llama/llama-4-maverick-17b-128e-instruct-fp8`, `mistralai/mistral-medium-2505`, `mistralai/mistral-small-3-1-24b-instruct-2503`. |
| 2 | Same list with `tech_preview=true` | Still no Granite Vision. |
| 3 | `POST eu-de/ml/v1/text/chat` with `ibm/granite-vision-3-2-2b`, `-3-3-2b`, `-4-1-4b` against project `1a6c81fb-…` | All three → `404 {"errors":[{"code":"model_not_supported", …}]}`. |
| 4 | Same against **us-south** | `403 user_authorization_failed` — the project lives in eu-de; a cross-region call is rejected before the model is even resolved. Not a model signal. |
| 5 | Rate limiting during probing | One `429 rate_limit` (instance limit ≈ 2 req/s). Probes were paced afterwards. |
| 6 | Control: `ibm/granite-4-h-small` text chat, eu-de | 200 OK (served `model_id` echoed; ~1.4 s). Credentials, project and region are therefore correct. |

## What IBM's documentation says

* watsonx.ai **v2.4 release notes**: `ibm/granite-vision-3-2-2b` and `pixtral-12b`
  **removed** from the multitenant catalogue.
* IBM Granite product page (foundation models table): `granite-vision-3-3-2b`
  and `granite-vision-4-1-4b` are listed as **“Deploy on demand only”** — a
  dedicated, hourly-billed deployment that must be created in a *deployment
  space* on a **Standard** (paid) watsonx.ai Runtime plan; they are not
  pay-per-token.
* Model lifecycle page: deprecated models answer with a `warnings` block;
  removed/unavailable ids answer `404 model_not_supported` — exactly what we observe.

## Classification

| Hypothesis | Verdict | Evidence |
|---|---|---|
| Code defect in our client | **No** | Same request shape works for `granite-4-h-small` and `llama-4-maverick` (image_chat) in eu-de. |
| Wrong region | **No** (for availability) | Six regions enumerated; none serves Granite Vision multitenant. us-south 403 is a project/region mismatch, not a model issue. |
| Missing IAM permission | **No** | Permission failures surface as 401/403, not 404; the key lists specs and runs chat in its own region. |
| Model retired | **Partly** | `granite-vision-3-2-2b` (tutorial id) is removed. |
| Commercial / deployment model | **Yes — root cause** | The current Granite Vision generations (3.3-2b, 4.1-4b) exist only as **Deploy-on-Demand** on a paid plan. The operator's Lite/sandbox project cannot create one, so there is nothing to call. |

## Decision and mitigation (implemented in this branch)

1. **Default stays honest.** Vision continues on `llama-4-maverick-17b-128e-instruct-fp8`
   (configurable), labelled per item in `analysis_source`; reasoning on
   `ibm/granite-4-h-small`. Nothing is called "Granite" that isn't.
2. **Config-only path to real Granite Vision.** If the operator deploys
   `granite-vision-4-1-4b` on demand, setting `WATSONX_VISION_DEPLOYMENT_ID=<deployment id>`
   routes vision calls to `POST /ml/v1/deployments/{id}/text/chat` (body without
   `model_id`/`project_id`, as IBM requires); `WATSONX_REASONING_DEPLOYMENT_ID`
   does the same for the stylist. Provenance is still taken from the **served**
   `model_id` in the response, so the UI label follows reality, not config.
   Unit tests: `backend/tests/test_watsonx_stylist.py::TestDeployOnDemandRouting`
   (3 tests: endpoint + body shape; provenance follows served model;
   multitenant contract unchanged when unset).
3. **Not done, and why:** no Deploy-on-Demand instance was created. It is a
   billing commitment (hourly, dedicated hardware) that requires explicit
   operator authorisation; this repo must not incur it.

## Operator checklist to enable Granite Vision later

1. Upgrade the watsonx.ai Runtime instance in eu-de to **Standard**.
2. Create a deployment space; deploy `ibm/granite-vision-4-1-4b` on demand.
3. Set `WATSONX_VISION_DEPLOYMENT_ID` (and optionally
   `WATSONX_VISION_MODEL_ID=ibm/granite-vision-4-1-4b` for status display).
4. Run `python scripts/watsonx_smoke.py` — it reports the served `model_id`.
5. Watch cost: a deployment bills while it exists, not per request.

## Status

| Item | State |
|---|---|
| Availability question | **VERIFIED LIVE** (answered: Deploy-on-Demand only) |
| Deploy-on-Demand routing | **MOCKED** (unit tests); **NOT VERIFIED LIVE** (no deployment exists) |
| Default vision model (`llama-4-maverick`) | **VERIFIED LIVE** (session 1 smoke) |
