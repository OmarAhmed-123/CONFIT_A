import { useQuery } from '@tanstack/react-query';
import { request } from '../services/apiClient';
import { LocalizedError, msg } from '../i18n/messages';

/**
 * Admin readiness reads the SAME public /health verdict as operators and
 * release probes. This module also validates the runtime payload: a TypeScript
 * generic is erased at runtime, so a 200 containing malformed/partial JSON is
 * UNKNOWN, never green-by-default and never a render-time crash.
 */

export interface PlatformReadiness {
  status: string;
  ready: boolean;
  blocking_capabilities: string[];
  degraded_capabilities: string[];
  /** Names only. Details remain on the admin-only /health/ready endpoint. */
  unprobed_capabilities: string[];
  version?: string;
}

export type ReadinessVerdict = 'ready' | 'not_ready' | 'unknown';

const stringArray = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every((item) => typeof item === 'string');

/**
 * Fail-closed runtime contract parser. Missing capability arrays, non-boolean
 * `ready`, malformed JSON shapes, and partial responses all throw into
 * React Query's error path -> verdict `unknown`. UNKNOWN != READY.
 */
export function parsePlatformReadiness(value: unknown): PlatformReadiness {
  if (!value || typeof value !== 'object') {
    throw new LocalizedError(msg('errors.readiness_malformed_object'));
  }
  const payload = value as Record<string, unknown>;
  if (
    typeof payload.status !== 'string' ||
    typeof payload.ready !== 'boolean' ||
    !stringArray(payload.blocking_capabilities) ||
    !stringArray(payload.degraded_capabilities) ||
    !stringArray(payload.unprobed_capabilities)
  ) {
    throw new LocalizedError(msg('errors.readiness_malformed_fields'));
  }
  return {
    status: payload.status,
    ready: payload.ready,
    blocking_capabilities: [...payload.blocking_capabilities],
    degraded_capabilities: [...payload.degraded_capabilities],
    unprobed_capabilities: [...payload.unprobed_capabilities],
    version: typeof payload.version === 'string' ? payload.version : undefined,
  };
}

export function usePlatformReadiness(): {
  verdict: ReadinessVerdict;
  readiness: PlatformReadiness | null;
  isLoading: boolean;
} {
  const query = useQuery({
    queryKey: ['platform', 'readiness'],
    queryFn: async () => parsePlatformReadiness(await request<unknown>('/health')),
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
