# Production outage 2026-09-21 — schema gate, and the storage switch that was never flipped

هذا التقرير **ليس لتقييم أي شخص ولا لمعاقبة أحد**. الهدف منه: نعرف إيه اللي حصل
بالظبط، وإزاي اكتشفناه، وإيه اللي اتصلّح، وإيه اللي **لسه** محتاج شغل — بدليل
قابل للتكرار، لا بادّعاء.

---

## 1. What happened

Between **11:00:41Z** and **11:11:28Z** the whole API at
`https://confit-a.vercel.app` was unreachable. Every path — including
`/api/v1/health` — answered:

```
HTTP 500
A server error has occurred
FUNCTION_INVOCATION_FAILED
pdx1::8p827-1789988577935-e1638a7b622b
```

No body. No error code. No cause. 12 consecutive requests over ~36 s: **0×200,
12×500** — so it was deterministic, not a cold start.

## 2. How it was narrowed down

Three independent observations, each of which rules something out:

**(a) It was not the code.** Five deployments from four different branches,
built from different source, answered identically:

| deployment | branch |
|---|---|
| `dpl_D3yLM2spJcETnGZmZeVzXdxwSc4U` | `main` (production) |
| `dpl_7VsdmKA1NvDDQHpxpDcQksDv85in` | `fix/vton-photomatch-audit-closure` |
| `dpl_BQaxjFAYRqbJF6D3kqukisw6ddyL` | `fix/admin-governance-audit-telemetry` |
| `dpl_14biZjF8PVygBBo7EVZGVvHVnZ69` | `g4-wardrobe-lifecycle-closure` |
| `dpl_9T3eiEvTGmFgbYuCd7cRa3heLZpw` | `feat/outfit-composer-mylooks-sharing` |

**(b) It was not the build.** The build log of a deployment that *worked*
(`dpl_HFbDPjopPLD6455hPjgG2y4yadmx`, 08:51:50Z, commit `fdeff3b6`) and the one
that did not (`dpl_D3yLM2spJcETnGZmZeVzXdxwSc4U`, 11:00:41Z, commit `81b71158`)
are line-for-line equivalent on everything that matters:

```
Using CPython 3.14.7
Resolved 47 packages in 436ms      /  443ms
Installed 47 packages in 400ms     /  382ms
No Python version specified in .python-version, pyproject.toml, or Pipfile.lock. Using python version: 3.12
Installing required dependencies from api/requirements.txt...
Build Completed in /vercel/output [30s]   /  [34s]
```

**(c) It was not a new migration.** `git diff --name-only 8520492 81b7115 --
backend/alembic/versions/` is empty, and `expected_head_revision()` returned
`0017_audit_before_after_request_id` for both — the same head production was
serving successfully at 10:38:09Z.

Local reproduction with the production manifest ruled the import path out too:

```
$ pip install -r requirements.txt   # fresh venv, Vercel manifest only
$ ENVIRONMENT=production DATABASE_URL=postgresql://placeholder... \
  PYTHONPATH=. python -c "import api.index; print('vercel entrypoint import ok')"
vercel entrypoint import ok
```

## 3. Root cause

`FUNCTION_INVOCATION_FAILED` with no body means the Python function died during
**initialisation**, not while handling a request. The only code path that can do
that is the ASGI lifespan:

```python
# backend/app/main.py
from backend.app.core.schema_gate import enforce_at_startup
enforce_at_startup(engine, settings.ENVIRONMENT, logger=logger)
```

and, in `schema_gate.enforce_at_startup`:

```python
if is_prod and not ok and mode != "warn":
    raise SchemaDriftError(...)
```

Raising inside the lifespan aborts the invocation. Vercel then answers every
path — including `/health` — with an empty 500.

The trigger, read out of production `/health` the moment the service could
answer again:

```json
"schema": {
  "verdict": "drift",
  "expected_head": "0017_audit_before_after_request_id",
  "database_revision": "0018_outfit_share_lifecycle",
  "findings": ["database revision '0018_outfit_share_lifecycle' is unknown to
               this code (expected '0017_audit_before_after_request_id')"]
}
```

A preview deployment of `feat/outfit-composer-mylooks-sharing` (11:02:56Z)
applied migration **0018** to the **same Neon database production serves**,
while `main` still expected **0017**. Every later production cold start raised.

### The cascade — why this cost more than 11 minutes

1. `/health` died with everything else, so the one endpoint that could name the
   cause was the one that could not answer.
2. The release gate (`backend/scripts/check_release_schema_parity.py`) reads
   `/health` to decide whether a merge is safe. It reported
   `RELEASE GATE: INDETERMINATE — production ... answered HTTP 500` and exited 2,
   so **every merge to `main` was blocked repository-wide**.
3. The only remaining lever was `CONFIT_SCHEMA_GATE=warn`, added at 11:11:14Z —
   an override that switches the safety check off for the entire service — plus
   a redeploy at 11:11:28Z.

### The conceptual error

The gate had one word for two opposite situations:

| claim | meaning | correct action |
|---|---|---|
| this code **cannot** run on this schema | database is **behind**, or a required table/column is absent | stop the deploy (the 2026-09-03 incident) |
| this schema is **newer** than this code | every object the code needs is present | **serve** — nothing is unsafe |

`0018` had every table and column `0017` needed. Blocking protected nothing; it
converted a benign revision lag into a total outage.

## 4. What was changed

Commit `e5e1018` — `fix(schema-gate): stop a schema verdict from taking the whole API down`

- New verdict **`ahead`**: unknown/newer revision **and** no missing required
  table or column. Accepted in production, never reported as `ok`, so `/health`
  still says `degraded` and the lag stays visible.
- **`unreachable`** replaces the overloaded `unknown`, and is **not** fatal at
  startup. Requests are then refused by `request_guard_verdict` with a
  structured 503 carrying the finding.
- The 503 now names the condition: `DATABASE_UNREACHABLE` (check connectivity
  and credentials) vs `SCHEMA_DRIFT` (`alembic upgrade head`). Telling an
  operator to migrate an already-migrated database is exactly how this incident
  read from the outside.
- `SchemaGateReport.blocking` makes the distinction explicit: `drift` and
  `unmanaged` block; `ahead` and `unreachable` do not.

`ahead` is **earned by evidence, not granted by the revision string** — the same
unknown revision becomes a hard `drift` the moment a required object is gone, so
a destructive newer migration still stops the deployment. Both directions are
regression tests.

Commit `48f49b0` — `fix(release-gate): block on a database that is BEHIND, not on any difference`

`evaluate()` blocked on `observed != expected`. It now establishes direction
(migration chain when known, leading zero-padded number otherwise — which is the
case that matters, since production can carry a revision this tree has never
seen). When **neither** source yields a position it returns INDETERMINATE: it
does not infer a direction it could not establish.

Run against live production, not a fixture:

```
RELEASE GATE: PASS
  commit requires : 0017_audit_before_after_request_id
  production has  : 0018_outfit_share_lifecycle
  production is at 0018_outfit_share_lifecycle, which is AHEAD of this commit's head 0017_audit_before_after_request_id.
exit code 0
```

## 5. What is still NOT fixed — and it is the actual root cause

**Preview/branch deployments run their migrations against the same Neon
database that production serves.** Until each environment has its own database
branch, any feature branch that ships a migration puts production one revision
ahead of `main`, and the reverse is equally possible.

That is an infrastructure change — a Neon branch per environment plus a
per-environment `DATABASE_URL` — and it cannot be made safe from inside the
application. Recorded here rather than left implicit.

Also still open: the `CONFIT_SCHEMA_GATE=warn` override added during the
incident is a **production** env var. With the fixes above it should no longer
be needed, and leaving it in place means the gate stays off. It should be
removed once a deployment carrying these fixes is verified.

## 6. Storage — the switch that had never been flipped

The VTON audit's first gap was `storage.provider=local`,
`production_grade=false`, `writable=false` in production. The code that fixes it
(object storage, SSE on every write, a real round-trip probe gating
`production_grade`) merged earlier as PR #130 — but **the environment variables
were never set**, so production kept reporting `local`.

Verified working **before** touching the project settings — real
`PUT → GET → DELETE → confirm gone` through `S3StorageBackend` against the real
bucket, no mocks:

```
backend: S3StorageBackend
PUT  -> https://br-mute-waterfall-b2p706dr.storage.c-6.eu-central-1.aws.neon.tech/confit-a-media/audit-probe/... (0.94s)
exists: True
GET  -> match: True | 61 bytes
presign: yes https://br-mute-waterfall-b2p706dr.storage.c-6.eu-central-1.aws.neon.tech/...
DELETE -> True
after delete exists: False | read: None
  S3 read failed ...: An error occurred (NoSuchKey) when calling the GetObject operation
probe_storage: {'ok': True, 'verdict': 'ok', 'error': None, 'deleted': True,
                'url_prefix_ok': True, 'probe_ms': 1523.1}
storage_status: {'provider': 's3', 'production_grade': True}
```

Variables then set on the Vercel project `confit-a` (production + preview);
credentials stored `encrypted`, non-secrets `plain`. Nothing is committed to the
repository:

| variable | type |
|---|---|
| `STORAGE_PROVIDER=s3` | plain |
| `S3_BUCKET=confit-a-media` | plain |
| `AWS_REGION=eu-central-1` | plain |
| `S3_ENDPOINT_URL=https://br-mute-waterfall-b2p706dr.storage.c-6.eu-central-1.aws.neon.tech` | plain |
| `AWS_ACCESS_KEY_ID` | encrypted |
| `AWS_SECRET_ACCESS_KEY` | encrypted |
| `STORAGE_PROBE_ENABLED=true` | plain |
| `STORAGE_PROBE_TTL_SECONDS=300` | plain |

CSP needs no change: `vercel.json` already allows the Neon host in `img-src`
and `connect-src`.

## 7. Verification status

| item | status |
|---|---|
| Root cause identified with evidence | **VERIFIED** (production `/health` payload + build logs + empty migration diff) |
| `ahead` no longer aborts startup | **VERIFIED** (`test_newer_revision_with_every_required_object_is_ahead_not_drift`) |
| destructive newer migration still blocks | **VERIFIED** (`test_ahead_becomes_drift_when_a_required_object_is_missing`) |
| unreachable database stays diagnosable | **VERIFIED** (5 tests, `TestUnobservableDatabaseStaysDiagnosable`) |
| release gate passes on AHEAD, blocks on BEHIND | **VERIFIED** (11 tests + live run against production, exit 0) |
| full backend suite | **VERIFIED** — `1391 passed, 0 failed, 5 skipped` (220 s) |
| per-target runtime import gate | **VERIFIED** — `[vercel] OK`, `[docker] OK` |
| object storage round-trip | **VERIFIED** (real PUT/GET/DELETE/404 against the real bucket) |
| production reports `production_grade=true` | **NOT VERIFIED** — requires a build created after 11:44:32Z |
| per-environment database branches | **NOT VERIFIED — not implemented** (infrastructure change, out of application scope) |
| `CONFIT_SCHEMA_GATE=warn` override removed | **NOT DONE** — still present on production |
