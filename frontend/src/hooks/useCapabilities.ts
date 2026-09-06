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
export interface Capabilities {
  payments_live: boolean;
  payments_mode: 'live' | 'demo';
  bnpl_live: boolean;
  vton_gpu_ready: boolean;
  ai_stylist_live: boolean;
  bopis_live: boolean;
  bopis_store_count: number;
  storage_mode: string;
  returns_window_days: number;
}

export const HONEST_FALLBACK_CAPABILITIES: Capabilities = {
  payments_live: false,
  payments_mode: 'demo',
  bnpl_live: false,
  vton_gpu_ready: false,
  ai_stylist_live: false,
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
