# Catalog import — five-priority audit against the real repository

Scope: the five priorities in the new delivery brief (background import, multi-image
galleries, EGP→USD, brand-owned image sources, extra product fields), mapped to what
the code on this branch actually does. Every claim below names the file and line it
was read from. Nothing here is inferred from a report or a branch name.

Branch audited: `feat/catalog-csv-import-verified` (from `fix/wizard-reappearing`
@ `d97f374`), working tree uncommitted.

Status words are used strictly:

- **Present** — implemented, exercised by a test I ran, and the test fails if the
  behaviour is removed.
- **Partial** — some of the path exists; a named part is missing or silently drops
  data.
- **Missing** — no implementation, or a route/queue that points at nothing.

---

## Priority 1 — Durable background import

**Status: Missing.** The `202 Accepted` is cosmetic.

| Evidence | What it shows |
| --- | --- |
| `backend/app/controllers/brand_controller.py:469-522` | `POST /partner/catalog/confirm-import` (and its alias `/upload/csv`) declares `status_code=202`, then calls `catalog_service.process_csv_import(...)` inline and returns the finished result. The HTTP request lives for the entire import, including every image download and every render. |
| `backend/app/workers/celery_app.py:70` | Routes `backend.app.workers.tasks.bulk_catalog_import_task` to the `catalog_ingest` queue. |
| `backend/app/workers/tasks.py` | Defines `auto_tag_wardrobe_task`, `purge_expired_sessions_task`, `aggregate_analytics_task`, `release_expired_inventory_reservations_task`. **`bulk_catalog_import_task` does not exist.** The route points at nothing, so a worker would fail to resolve the task. |
| `docker-compose.yml:77-83` | A real `confit-celery-worker` service already consumes `catalog_ingest`. The infrastructure exists; the task does not. |
| `backend/app/models/catalog_import.py:7-33` | `CatalogImportJob` exists with `status` constrained to `queued/processing/completed/partially_completed/failed`, four row counters, `errors_json`, `created_at/started_at/completed_at`. There is **no** progress, attempt, lease/heartbeat, or result-payload column. |
| `backend/app/controllers/brand_controller.py:524-575` | `GET /partner/catalog/imports` and `GET /partner/catalog/imports/{job_id}` are real and brand-scoped (`repo.get_brand_import_jobs(bp["id"])`, `repo.get_import_job(job_id, bp["id"])` → 404 for another brand's job). These are the endpoints a poller needs; they already exist. |

Consequence, in the terms the brief uses: the browser cannot close, the connection
cannot be idle-timed-out by a proxy, and a 1000-row import cannot outlive
`task_time_limit` semantics because it is not a task. The job *row* is written and
updated, so the history is honest after the fact — the *execution* is not durable.

What the row can and cannot support today: counts and terminal states are persisted
(so a poller works), but there is no way to express "row 300 of 1000" or "attempt 2
of 3", and no lease, so two workers cannot safely race for the same job and a
crashed worker leaves a job in `processing` forever.

---

## Priority 2 — Multi-image product galleries

**Status: Partial — and the missing part fails silently, which is worse.**

| Evidence | What it shows |
| --- | --- |
| `backend/app/services/brand_catalog_service.py:1004-1010` | The `images` column is read and parsed as a JSON array… |
| `backend/app/services/brand_catalog_service.py:1010-1020` | …and only `parsed[0]` is kept, as `source_ref`. The remaining URLs are dropped. |
| `backend/app/services/brand_catalog_service.py:1020-1032` | Only `source_url` — the single hero `image_url`/`thumbnail_url` — is passed to `service.materialize(...)`. |
| `scripts/tooling/verify_catalog_csv_import_e2e.py` (run this session) | 12 imported products produced **120 image rows**, i.e. 10 per product: 5 ratios × 2 formats of **one** source photo. That is renditions, not a gallery. |

So a brand that supplies `images = ["front.jpg","back.jpg","detail.jpg"]` gets a
successful import, one reachable photo, and no warning that two of the three were
discarded. The brief's "never silently claim that an unsupported column was
imported successfully" is violated here today.

The storage/model side is *not* the blocker: `product_images` already holds many
rows per product with ordering/primary/attribution fields (`source_ref`,
`source_type`, `provider`, `attribution` are all written by `materialize`), and the
media delivery layer serves them. The gap is in the importer, plus a decision on
how the PDP gallery picks the primary image.

---

## Priority 3 — EGP→USD conversion

**Status: Missing, and deliberately so. This one needs a decision from you before
any code is written.**

| Evidence | What it shows |
| --- | --- |
| `backend/app/models/*` (grep for `exchange_rate`/`fx_rate`) | The only FX column anywhere is `orders.fx_rate_used` (`backend/app/models/commerce.py:121`), which records the rate an *order* was locked at. There is **no** rate table, no provider client, no freshness policy, no cached quote. |
| `backend/app/services/brand_catalog_service.py` (`_pricing_currency`, validation) | Catalogue rows are booked in USD; a row declaring another currency is refused at validation with "not an approved currency" rather than converted. |
| Earlier decision recorded in this repo's docs | EGP is display-only on the storefront (the cart converts for display at checkout time using the order-level FX lock). Pricing a *catalogue row* in EGP produced a ~53× disagreement between PDP and cart. The fix was to refuse it, not to convert it. |

The brief requires "obtain a verified exchange rate from the project's configured,
approved FX source" and "never assume an exchange rate, hardcode a rate without an
explicit approved policy". There is no approved source in the repository to call,
and inventing one (a static table, a magic constant, a fetch to an unvetted public
API) is exactly what both the brief and the standing project rules forbid.

**Blocked on:** which rate source is authoritative (a provider API and key, an
operator-maintained rate table, or the treasury rate already used for order FX),
what the freshness window is, and whether EGP rows should convert-and-accept or
stay refused with a clear message. Until that is answered, the honest behaviour —
refuse the row and say why — is what ships.

---

## Priority 4 — Brand-owned image sources

**Status: Present.** This is the one priority the earlier work on this branch
already delivered.

| Evidence | What it shows |
| --- | --- |
| `backend/app/core/config.py:664` | `CATALOG_IMPORT_ALLOW_OWN_IMAGES: bool = False` — secure default, flag-gated. |
| `backend/app/services/brand_catalog_service.py` (`IMAGE_SOURCES`, `image_source` column) | No flag → only the two approved stock hosts; `own` declared → brand-hosted URLs allowed, recorded with `source_type='own'` and a provenance attribution string. |
| `backend/app/core/net_guard.py` | Every fetch goes through the guard: scheme allowlist, redirect validation, loopback/private/link-local/reserved/metadata-address denial, size and content-type limits, timeouts. |
| `backend/tests/test_net_guard.py` | 26 tests, all passing (measured this session). |

Open item for this priority: the brief asks for tenant ownership verification on
every uploaded asset. Today the guard proves the *URL is safe*, not that the brand
*owns* it — nothing stops brand A from pointing at brand B's CDN path. That is an
authorization gap, not an SSRF gap, and it needs a decision about what "ownership"
can even mean for a public URL (domain allowlist per brand? signed upload instead?).

---

## Priority 5 — Additional product attributes

**Status: Partial.** The columns exist; the classification and the contract do not.

| Field | Reality | Current import treatment |
| --- | --- | --- |
| `is_active` | `backend/app/models/catalog.py:83`, `Boolean, default=True, nullable=False` — this is publication. An inactive product is out of the catalogue. | Not importable. Correct: publication is a moderation decision, not a CSV column. |
| `is_featured` | `backend/app/models/catalog.py:84`, `Boolean, default=False` — merchandising prominence. | Not importable. Needs an explicit rule (brand-settable vs admin-only) rather than silence. |
| `size_chart_json` | `backend/app/models/catalog.py:52`, `Text, default="{}"` — free-form JSON with **no schema anywhere**. | Not importable. Importing unvalidated JSON into a column the PDP renders is how a broken chart reaches production. |
| Gender / target audience | `Product.gender`, consumed by the stylist (`services/styling/garment_gender.py`). | Importable (this branch), with inference for rows that omit it. |
| Style/occasion tags | `Product.style_tags`, `product.occasion_tags`. | Importable (existing). |

Unknown headers are already reported rather than swallowed (the importer compares
against its own `OPTIONAL_FIELDS`/`HEADER_ALIASES` contract and the preview shows a
warning per unknown column), which is the behaviour the brief asks for.

---

## What this means for sequencing

Priority 4 is done. Priority 2 is a contained defect with a silent-data-loss
consequence — fix before anything else in the list, because it is a correctness bug
in a path brands already use. Priority 1 is the largest piece and is what the
brief calls priority one; the queue, the worker service and the job endpoints all
exist, so it is a task definition, a lease column, a progress column and a
`202`-that-tells-the-truth, not a new subsystem. Priorities 3 and 5 each need one
decision from you before code, and Priority 5 also needs a size-chart schema that
does not exist in the repo today.
