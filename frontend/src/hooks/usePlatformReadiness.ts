import { useQuery } from '@tanstack/react-query';
import { request } from '../services/apiClient';

/**
 * P1 closure (2026-09-22 admin audit): "readiness غير موحد مع واجهة الإدارة" —
 * `/health` reported `ready=false` (virtual_try_on blocking) while the admin
 * dashboard showed rich KPIs with no hint that the platform was not fully
 * operational.
 *
 * This hook reads the SAME capability registry the services publish — the
 * public `/health` endpoint — so the admin banner and the health verdict can
 * never disagree. Nothing here is a second opinion: the banner renders the
 * backend's own `blocking_capabilities` / `degraded_capabilities` verbatim.
 *
 * Fetch failure policy: the banner is governance signal, not a gate. If
 * /health itself cannot be reached the hook reports `unknown` and the banner
 * says so honestly (it never renders "all systems ready" from a fallback).
 */

export interface PlatformReadiness {
  status: string;
  ready: boolean;
  blocking_capabilities: string[];
  degraded_capabilities: string[];
  version?: string;
}

export type ReadinessVerdict = 'ready' | 'not_ready' | 'unknown';

export function usePlatformReadiness(): {
  verdict: ReadinessVerdict;
  readiness: PlatformReadiness | null;
  isLoading: boolean;
} {
  const query = useQuery({
    queryKey: ['platform', 'readiness'],
    queryFn: () => request<PlatformReadiness>('/health'),
    // Readiness can flip during an incident; keep it reasonably fresh but
    // never hammer the endpoint from an idle dashboard.
    staleTime: 1000 * 60,
    refetchInterval: 1000 * 120,
    retry: 1,
  });

  const readiness = query.data ?? null;
  let verdict: ReadinessVerdict = 'unknown';
  if (readiness) {
    verdict = readiness.ready ? 'ready' : 'not_ready';
  }
  return { verdict, readiness, isLoading: query.isLoading };
}
