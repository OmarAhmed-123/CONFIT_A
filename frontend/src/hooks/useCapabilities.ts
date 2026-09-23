import { useQuery } from '@tanstack/react-query';
import { catalogService } from '../services/apiServices';
import { queryKeys } from '../lib/queryClient';

/**
 * J-01 marketing honesty (2026-09-06 remediation): server-authoritative
 * capability flags. Every commerce/trust claim in the UI binds to these —
 * if the flag is off, the UI shows a Demo/coming-soon label instead of
 * promising a capability the platform cannot deliver. When the flags cannot
 * be fetched, all optimistic claims degrade to their honest (demo) wording.
 */
/**
 * Canonical engine states as published by the backend. `engine_state` is a
 * machine discriminator, so the UI localizes its own sentence from it rather
 * than rendering the backend's English `user_message` into an Arabic page.
 */
export type VtonEngineState =
  | 'available'
  | 'cold_start'
  | 'temporarily_unavailable'
  | 'misconfigured';

export interface Capabilities {
  payments_live: boolean;
  payments_mode: 'live' | 'demo';
  bnpl_live: boolean;
  /**
   * MEASURED GPU readiness (live probe of the worker).
   *
   * Until 2026-09-22 the backend derived this from `bool(VTON_WORKER_URL)`, so
   * it read `true` on a deployment where every try-on job failed. It is now the
   * same verdict `/try-on/capabilities` publishes. Prefer
   * `useTryOnAvailability()` when gating behaviour: it also carries the reason
   * and the retry window.
   */
  vton_gpu_ready: boolean;
  /** Canonical state — identical to `/try-on/capabilities`.`engine_state`. */
  vton_engine_state: VtonEngineState | string;
  /** Whether this deployment offers try-on at all. `false` = not offered. */
  vton_offered: boolean;
  /** Whether a job submitted now can produce a render (ready or cold start). */
  vton_renderable: boolean;
  ai_stylist_live: boolean;
  /**
   * MEASURED: can a consumer photo actually be persisted right now?
   *
   * Server-derived from the storage probe (put/get/delete round trip where the
   * deployment enables it). Do NOT gate uploads on `storage_mode`: that is the
   * provider's *name*, and a deployment configured for s3 with an unreachable
   * bucket or a revoked credential still reports "s3" while every upload fails.
   */
  photo_upload_available: boolean;
  bopis_live: boolean;
  bopis_store_count: number;
  /** Provider NAME for display/telemetry only. Never a readiness verdict. */
  storage_mode: string;
  returns_window_days: number;
}

export const HONEST_FALLBACK_CAPABILITIES: Capabilities = {
  payments_live: false,
  payments_mode: 'demo',
  bnpl_live: false,
  vton_gpu_ready: false,
  vton_engine_state: 'temporarily_unavailable',
  vton_offered: false,
  vton_renderable: false,
  ai_stylist_live: false,
  photo_upload_available: false,
  bopis_live: false,
  bopis_store_count: 0,
  storage_mode: 'local',
  returns_window_days: 30,
};

export function useCapabilities() {
  const query = useQuery({
    queryKey: queryKeys.catalog.capabilities(),
    queryFn: () => catalogService.getCapabilities(),
    staleTime: 1000 * 60 * 5,
    gcTime: 1000 * 60 * 30,
    retry: 1,
  });
  return {
    capabilities: query.data ?? HONEST_FALLBACK_CAPABILITIES,
    isLoading: query.isLoading,
  };
}
