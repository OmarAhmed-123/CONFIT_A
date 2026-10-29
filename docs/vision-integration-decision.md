# Decision record — garment vision: Granite Vision vs alternative model vs manual entry

**Decision (2026-10-28, re-confirmed 2026-10-29):** keep three explicit, labelled paths
and let configuration — not code — choose between them. No Deploy-on-Demand instance
is created by this project (billing commitment requiring operator authorisation).

| Option | Availability on this account | Decision | Labelling |
|---|---|---|---|
| **A. IBM Granite Vision** (`granite-vision-3-3-2b`, `granite-vision-4-1-4b`) | **Not callable**: 404 `model_not_supported` in all six multitenant regions; Deploy-on-Demand only on a paid plan; tutorial id `granite-vision-3-2-2b` withdrawn by IBM | Code path kept and unit-tested (`TestDeployOnDemandRouting`); enabled only by `WATSONX_VISION_DEPLOYMENT_ID` | `analysis_source` = served `model_id` from the response |
| **B. Alternative watsonx multimodal model** (`meta-llama/llama-4-maverick-17b-128e-instruct-fp8`, default) | Live, verified eu-de | **Default** for photo analysis — on watsonx.ai, same governance surface, but **not Granite and never called Granite** | `analysis_source="meta-llama/…"`; UI shows the model name |
| **C. Manual entry / user correction** | Always | Always available; every AI-filled field is editable; edits recorded | `analysis_source="manual (was …)"`; no AI badge |
| D. Non-IBM vision provider | n/a | **Rejected** — would silently substitute another vendor for the IBM stack | — |

Why not block the feature until Granite Vision exists? Because the stylist's value
(reasoning over an *accurate* closet) is delivered by B + C today, and A is a
configuration flip with provenance already following the served model. Why not use
B and call it "Granite"? Because that would be a false claim; the acceptance rule in
`IBM_WATSONX_STYLIST_ACCEPTANCE.md` forbids it.

Evidence and operator checklist to enable A: `GRANITE_VISION_AVAILABILITY_INVESTIGATION.md`.
Status of A: **BLOCKED (account/commercial), not a code defect.**
