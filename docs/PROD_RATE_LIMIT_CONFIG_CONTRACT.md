# Production Rate-Limit Configuration Contract — Cycle 9

**Date:** 2026-10-10 (Africa/Cairo)  
**Workstream:** 003-guest-order-trust-returns  
**Related Code:** `backend/app/core/rate_limit.py`, `backend/app/controllers/telemetry_controller.py`, `backend/app/core/config.py`

## 1. Goal

Make the rate limiter's **configured** vs **active** enforcement state observable without leaking secrets, and document what must be set for production multi-instance deployments to get a global quota.

## 2. Environment Variables

### 2.1 `RATE_LIMIT_STORAGE_URL` (explicit switch, preferred)

- **Type:** Optional[str], default `None`
- **Semantics:** When set to a shared-store URI (`redis://`, `rediss://`, `unix://`, `memcached://`, `mongodb://`), the limiter uses that store.
- **Precedence:** Highest — wins over `REDIS_URL`.
- **Example:** `RATE_LIMIT_STORAGE_URL=redis://:s3cret@redis.example.com:6379/0`

### 2.2 `REDIS_URL` (operator-provided fallback)

- **Type:** str, default `redis://localhost:6379/0` in `Settings` for dev convenience
- **Semantics:** Only used for rate limiting when **read from environment** (`os.environ.get("REDIS_URL")`) and its scheme is a shared-store scheme. The code deliberately does **NOT** use `settings.REDIS_URL` default to avoid fake distributed limiter (loopback dial in serverless would look shared but be per-instance).
- **Source tracking:** `configured_storage_uri()` records `configured_from` as `"RATE_LIMIT_STORAGE_URL"` or `"REDIS_URL (operator-provided)"` or `"default (in-process counters)"`.

### 2.3 Default

- When neither explicit switch nor operator env points to a shared store: `memory://`
- Honest default: per-instance counters, quota semantics `"per-instance: bounds a client's burst against one warm instance; it is NOT a global quota"`
- This default is intentional — synthesizing `redis://localhost` would be a fake global quota.

## 3. What Must Be Configured for Production

- **Multi-instance deployments (Vercel serverless, containers, K8s):** Must set `RATE_LIMIT_STORAGE_URL` to a managed Redis (or provide `REDIS_URL` env pointing to shared Redis) to get global quota.
- **Single-instance dev/CI:** No action needed — memory store is honest and bounds burst per instance.
- **No new dependency:** Redis integration already supported via `limits` library; `docker-compose.yml` defines `redis:7-alpine` for local testing.

## 4. Enforcement Behavior

### 4.1 Per-Process (memory://)

- Each warm instance keeps own counters.
- `30/minute` on guest-order endpoints bounds burst against **one instance**, not global.
- An attacker routed to different instances can multiply allowance by number of warm instances — per-instance bound still useful (stops single-instance flood) but NOT global.

### 4.2 Global (redis://)

- `build_limiter(shared_uri)` sets `swallow_errors=True, in_memory_fallback_enabled=True`, `key_style="endpoint"` (one bucket per logical endpoint, not per URL spelling), `client_key` hashes credential first (`tok:<sha256>`) so authenticated and guest callers isolated, IP fallback via trusted-proxy rightmost hop policy (Vercel `x-vercel-forwarded-for`, `x-real-ip`, trusted proxy CIDRs).
- `30/minute` becomes global: every instance counts against one quota.

### 4.3 Degradation

- On shared store unreachable, limiter degrades to in-process counters (per-instance) and does **NOT** 500 the request.
- Degraded still enforces per-instance limit (429 after fallback).
- Negative control: without fallback flags, same outage would 5xx — proves fallback is load-bearing.
- Implementation: `slowapi.Limiter` exposes `_storage_dead` bool; when True + fallback enabled, active store is memory per-instance not global.

## 5. Observability — Configured vs Active

### 5.1 Old report (Cycle 8)

`rate_limit_store_report()` returned only configured store:
```json
{
  "store": "redis",
  "shared_across_instances": true,
  "configured_from": "RATE_LIMIT_STORAGE_URL",
  "quota_semantics": "global: every instance counts against one quota",
  "on_store_failure": "degrades to in-process counters (per-instance) and reports it"
}
```
Problem: static text `"degrades ... and reports it"` — not live boolean, operator cannot tell if actually degraded.

### 5.2 New report (Cycle 9)

`rate_limit_runtime_report(limiter_instance, storage_uri)` distinguishes 4 states:

1. **Shared configured, operating:** `configured.shared=True`, `active.shared=True`, `degraded=False`
2. **No shared configured, in-process:** `configured.shared=False`, `active.shared=False`, `degraded=False`
3. **Shared configured but unavailable, degraded to in-process:** `configured.shared=True`, `active.shared=False`, `active.store=memory`, `degraded=True`, `active_reason="shared store configured but unreachable — degraded to in-process counters"`, `quota_semantics="per-instance (degraded): ... NOT global quota until shared store recovers"`
4. **Undetermined fallback:** returns configured report with `degraded=False`

Shape:
```json
{
  "configured": { "store": "redis", "shared_across_instances": true, "configured_from": "...", "quota_semantics": "global...", "on_store_failure": "degrades..." },
  "active": { "store": "memory", "shared_across_instances": false, "degraded": true, "quota_semantics": "per-instance (degraded)...", "active_reason": "shared store configured but unreachable..." },
  "degraded": true
}
```

`rate_limit_health_report()` is the health surface wrapper: returns same plus top-level backward compat fields reflecting **active** enforcement (`store`, `shared_across_instances`, `quota_semantics`, `configured_from`, `on_store_failure`) plus nested `configured`/`active`/`degraded`/`active_reason`.

Active check is cheap boolean `_storage_dead`, not a Redis ping — no network hop per health probe.

### 5.3 Health Endpoints

- `/api/v1/health` (public): does **NOT** include `rate_limit` — topology disclosure avoidance. Verified by `test_the_operator_surface_publishes_the_store_and_the_public_one_does_not`.
- `/api/v1/health/ready` (operator, ADMIN_ROLES): includes `rate_limit: rate_limit_health_report()` — operator surface only, access controlled via `require_role(ADMIN_ROLES)`.
- Probe payload `_probe()` includes `rate_limit` from health report.

### 5.4 Secret Safety

- Reports expose only scheme names (`"redis"`, `"memory"`) not full URI, no password, no host:port, no `://`.
- Tests assert `"://"` and `"@"` and `"s3cret"` not in report blob across all states.

## 6. 429 Contract Preserved

- Handler `rate_limit_exceeded_handler`: envelope `{"error": {"code":"RATE_LIMITED","message":"Too many requests...","details":{"limit","retry_after_seconds"}}}`, header `Retry-After` from window stats, honest omission if unreadable.
- Tests `test_rate_limiting.py`: 8 PASS including `test_429_carries_a_machine_code_and_a_retry_delay`, `test_every_expensive_consumer_endpoint_declares_a_limit` (now file-relative, includes guest-order endpoints).

## 7. Verification (Cycle 9)

- `backend/.venv` redis library 8.1.0 present, no redis-server binary/docker in sandbox — shared-store integration UNVERIFIED in this env, documented per instruction not to mock cross-process sharing nor use prod creds.
- Degradation simulated via `_storage_dead=True` — matches slowapi behavior on failure.
- New tests `test_rate_limit_degradation_observability.py`: 7 PASS covering explicit shared healthy, in-process healthy, simulated failure degraded bounded per-instance, recovery, no sensitive disclosure, on_store_failure preserved, cheap boolean no network.
- Existing: `test_rate_limit_store.py` 7 PASS 4 SKIP, `test_rate_limit_store_source.py` 5 PASS, `test_rate_limit_identity.py` 12 PASS, `test_rate_limiting.py` 8 PASS, guest trust 34 PASS.

## 8. Production Checklist

- [ ] Set `RATE_LIMIT_STORAGE_URL=redis://...` or `REDIS_URL` env to managed Redis for multi-instance
- [ ] Verify `/health/ready` shows `store=redis`, `shared_across_instances=true`, `degraded=false`, `configured.store=redis`, `active.store=redis` when healthy
- [ ] Simulate Redis outage (block port) — verify `/health/ready` flips to `store=memory`, `shared=false`, `degraded=true`, `configured.store=redis`, `active.store=memory`, requests still 200 then 429 per-instance, not 500
- [ ] Verify recovery — Redis back, `/health/ready` returns to `degraded=false`, `store=redis`
- [ ] Verify public `/health` does NOT contain `rate_limit`
- [ ] Verify no secrets in logs or health payloads

## 9. References

- `backend/app/core/rate_limit.py` — `configured_storage_uri()`, `is_shared_store()`, `build_limiter()`, `_is_limiter_degraded()`, `rate_limit_store_report()`, `rate_limit_runtime_report()`, `rate_limit_health_report()`
- `backend/app/controllers/telemetry_controller.py` — `_probe()` returns `rate_limit_health_report()`
- `docker-compose.yml` — `redis:7-alpine` service
- Tests: `test_rate_limit_store.py`, `test_rate_limit_degradation_observability.py`
