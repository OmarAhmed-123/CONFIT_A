# CONFIT_A - Full Production Remediation Matrix
## Evidence-Driven - No Fabrication
## Branch: fix/full-production-remediation | Date: 2026-05-11

| ID | Component | Issue | Root Cause | Evidence | Severity | Fix | Files Changed | Tests | Verification | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| C1 | Commerce Repo | Cart Merge Race Condition | No FOR UPDATE locks in merge_guest_into_user_cart | Code review: plain query without with_for_update | HIGH | Add SELECT FOR UPDATE on both carts, transaction boundary, consistent lock order user->guest | commerce_repository.py | Concurrency test | pytest | FIXED |
| C2 | Commerce Controller | Checkout Session Persistence | Token generated but never persisted, get always 404 | Code: create_checkout_session generates token but doesn't save | CRITICAL | Implement CheckoutSession model + Alembic 0009 migration + repo methods with locks + controller endpoints POST/GET/confirm | commerce_controller.py, models/commerce.py, models/__init__.py, commerce_repository.py, alembic/versions/0009 | test_checkout_session_persistence | pytest | FIXED |
| C3 | Frontend apiClient | CSRF Lifecycle | Need to verify complete CSRF flow | Code: apiClient.ts implements getCsrfToken + X-CSRF-Token, backend sets cookie | HIGH | Verify cookie creation, header transmission, add tests for valid/missing/invalid CSRF | apiClient.ts, backend/app/main.py, tests/test_cookie_auth.py | CSRF tests | pytest | IN PROGRESS |
| C4 | Commerce UI | Payment Demo Safety | Demo payments could be confused with real | PAYMENTS_LIVE=false uses demo adapter, no banner | MEDIUM | Add unmistakable demo banner in CheckoutView (amber, ⚠️ Demo Payment Mode, payment_mode demo) | CheckoutView.tsx | Manual + build | Build | FIXED |
| C5 | Wardrobe Service | Synchronous Upload/Analysis | Upload does analysis synchronously, Vercel 60s timeout | upload_items validates, stores, analyzes same request | HIGH | Async: enqueue Celery auto_tag_wardrobe_task, return processing status immediately, fallback inline in dev | wardrobe_service.py, tasks.py, storage_service.py | test_wardrobe_upload_async | pytest | FIXED |
| C6 | ProductDetailView | BOPIS Failure Handling | Silently converts API failure to empty list | .catch(() => setBopisStores([])) | MEDIUM | Differentiate loading/success/empty/error states, inline error + retry, no silent swallow | ProductDetailView.tsx | Frontend build | Build | FIXED |
| C7 | Cart Store | Optimistic Update + Rollback | No rollback on failure for updateQuantity/removeItem | Direct server call, no prev capture | MEDIUM | Optimistic with prev state capture, rollback on failure, server reconciliation for authoritative totals | cartStore.ts | Manual | Build | FIXED |
| C8 | i18n | Dynamic RTL | Need RTL handling | i18n.ts already implements dir rtl/ltr - VERIFIED | LOW | Already implemented | i18n.ts | Manual language switch | Build | VERIFIED |
| C9 | Vercel | Build Determinism | npm install vs npm ci | vercel.json used npm install | MEDIUM | Change to npm ci | vercel.json | npm ci + build | Build | FIXED |
| C10 | API | Python Path Hacks | sys.path.insert fragile | api/index.py had 3-path loop | LOW | Simplify to parent_dir only | api/index.py | Import check | Import | FIXED |
| C11 | Inventory | Reservation Expiry | Held reservations never expire, stock leak | No cleanup job, no TTL | CRITICAL | Celery task every 15min with FOR UPDATE locks | tasks.py, celery_app.py | test_inventory_expiry | pytest | FIXED |
| C12 | Commerce | Server-Authoritative | Frontend must not be trusted for totals | _line_items_from_cart calculates server-side - VERIFIED | LOW | Tampering test proving manipulated totals ignored | commerce_service.py | tampering test | pytest | VERIFIED |
| C13 | Commerce | BOPIS Atomicity | Global stock deducted before store check | sku.stock_level -= qty before store_inv check | HIGH | 2-phase: validate all first, then modify | commerce_service.py | BOPIS tests | pytest | FIXED |
| C14 | Styling | Grounding Validation | AI text must be verified against catalog | No verification brand names appear | MEDIUM | Add _verify_grounding() checking brand/title presence, fallback deterministic | orchestrator.py | test_stylist_grounding | pytest | FIXED |
| C15 | Styling | Budget Honesty | budget_note must be visible | budget_note exists but not in UI | MEDIUM | Show within/over budget badge + budget_note in VirtualStylistDrawer | VirtualStylistDrawer.tsx, composer.py | Manual + build | Build | FIXED |
| C16 | Discovery | Wardrobe-First | Should leverage owned items | getOutfitSuggestions returns owned_count - VERIFIED | LOW | Ensure DiscoverView wardrobe-first option | DiscoverView.tsx | Manual | Build | VERIFIED |
| C17 | VTON | Modal Crash-Loop Root Cause | container fails to start ModuleNotFoundError pipeline | Missing model/__init__.py, package layout | P0 | Stage catvton_pkg with utils.py + model/__init__.py + pipeline/utils/attn_processor, honest degraded health | modal_app.py | Modal deploy + logs | Modal | FIXED |
| C18 | VTON | Readiness Architecture | Distinguish PROCESS_ALIVE vs MODEL_READY | model_loaded flag exists but no explicit readiness endpoint | HIGH | Implement /readiness endpoint returning 503 if not ready, ready flag in health | modal_app.py | health check | Modal | FIXED |
| C19 | VTON | Health Check | Backend must verify readiness before jobs | No health check before submit | HIGH | Add health+readiness check with 3 retries + exponential backoff before job dispatch | tryon_service.py | test_vton_integrity | pytest | FIXED |
| C20 | VTON | Failure Isolation | Failed init must not crash loop | try/except in load_model with load_error preserved - VERIFIED | MEDIUM | Ensure logs actionable, avoid infinite crash | modal_app.py | Logs | Modal | VERIFIED |
| C21 | No-Photo Fit | Confidence Score | No confidence communicated | No confidence score | MEDIUM | Add confidence based on inputs count (40%+15% per extra), is_estimated flag, disclosure | no_photo_fit_service.py | test | pytest | FIXED |
| C22 | Frontend | React Query Usage | Manual useEffect for server state | useCatalogViewModel uses useEffect, should use React Query | MEDIUM | Evaluate React Query for server state, keep Zustand for client | viewmodels/*.ts | Build | Build | TODO (low priority, existing works) |
| C23 | Frontend | Image Performance | No lazy loading, srcset | <img> without lazy | MEDIUM | Add loading=lazy, decoding=async, onError fallback placeholder | ProductDetailView.tsx, DiscoverView.tsx | Build | Build | FIXED |
| C24 | Storage | Production Storage | Local storage ephemeral on Vercel/Render | STORAGE_PROVIDER=local default | HIGH | Created storage_service abstraction with local+S3/R2 backends, honest failure, prod warning, config for S3 env vars | storage_service.py, config.py, wardrobe_service.py | Manual | Build | FIXED |

## Previous Fixes Already Applied (from fix/production-hardening-critical cherry-pick)
- C9, C10, C11, C13 fixed and verified (225 tests pass, build passes)
- C8 verified already implemented
- C12 verified server-authoritative
- C16 verified wardrobe-first exists
- C20 verified failure isolation exists

## This Session Fixes (2026-05-11)
- C1: FOR UPDATE locks
- C2: CheckoutSession model + migration + repo + controller
- C4: Demo payment banner
- C5: Async wardrobe pipeline via Celery
- C6: BOPIS failure handling
- C7: Cart optimistic rollback
- C14: Grounding validation
- C15: Budget honesty UI
- C17-19: VTON Modal crash-loop, readiness, health retry
- C21: No-photo fit confidence
- C23: Image performance lazy + fallback
- C24: Storage abstraction S3/R2 + prod warning

## Remaining
- C3: CSRF lifecycle tests (needs test file creation)
- C22: React Query (low priority, can be deferred - existing Zustand works, not critical for prod safety)
