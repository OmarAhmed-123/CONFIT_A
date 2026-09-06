/**
 * CYCLE-3 (BLOCKER J): transparent session-renewal contract.
 *
 * - 401 on a normal endpoint → ONE cookie-based /auth/refresh → ONE retry.
 * - If renewal fails: local session evidence purged, 'confit:session-expired'
 *   dispatched, and the ORIGINAL 401 surfaces (never a loop, never a fake).
 * - /auth/refresh itself never recurses.
 * - Parallel 401s share a single refresh (single-flight).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { request, ApiError, SESSION_EXPIRED_EVENT } from '../apiClient';

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const OK = () => jsonResponse(200, { ok: true });
// factory: a Response body can be read exactly once — parallel tests need fresh objects
  const UNAUTHORIZED = () => jsonResponse(401, { error: { code: 'AUTH_REQUIRED', message: 'expired', details: {} } });

describe('session auto-refresh (BLOCKER J)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    localStorage.clear();
    localStorage.setItem('confit_user', '{"id":1}');
  });

  it('401 → refresh → retry once → success', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(UNAUTHORIZED())                                   // original call
      .mockResolvedValueOnce(jsonResponse(200, { access_token: 'a', refresh_token: 'r', user: { id: 1 } })) // /auth/refresh
      .mockResolvedValueOnce(OK());                                          // retry
    vi.stubGlobal('fetch', fetchMock);

    const out = await request<{ ok: boolean }>('/wardrobe/items');
    expect(out.ok).toBe(true);
    expect(fetchMock.mock.calls.length).toBe(3);
    const refreshCall = fetchMock.mock.calls[1];
    expect(String(refreshCall[0])).toContain('/auth/refresh');
    // session evidence preserved on success
    expect(localStorage.getItem('confit_user')).toBe('{"id":1}');
  });

  it('failed refresh purges evidence, fires session-expired, surfaces the original 401', async () => {
    const expiredListener = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, expiredListener);
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(UNAUTHORIZED())
      .mockResolvedValueOnce(jsonResponse(401, { error: { code: 'AUTH_FAILED', message: 'Refresh token expired.', details: {} } }));
    vi.stubGlobal('fetch', fetchMock);

    const err = (await request('/wardrobe/items').catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(401);
    expect(fetchMock.mock.calls.length).toBe(2); // no retry after failed renewal
    expect(localStorage.getItem('confit_user')).toBeNull();
    expect(expiredListener).toHaveBeenCalledTimes(1);
    window.removeEventListener(SESSION_EXPIRED_EVENT, expiredListener);
  });

  it('/auth/refresh itself never triggers the renewal path', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValue(jsonResponse(401, { error: { code: 'AUTH_FAILED', message: 'Refresh token expired.', details: {} } }));
    vi.stubGlobal('fetch', fetchMock);

    const err = (await request('/auth/refresh', { method: 'POST', body: '{}' }).catch((e) => e)) as ApiError;
    expect(err.status).toBe(401);
    expect(fetchMock.mock.calls.length).toBe(1); // exactly one call, no recursion
  });

  it('retried request that 401s again surfaces the error (no loop)', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(UNAUTHORIZED())
      .mockResolvedValueOnce(jsonResponse(200, { access_token: 'a', refresh_token: 'r', user: { id: 1 } }))
      .mockResolvedValue(UNAUTHORIZED()); // retry still 401
    vi.stubGlobal('fetch', fetchMock);

    const err = (await request('/wardrobe/items').catch((e) => e)) as ApiError;
    expect(err.status).toBe(401);
    expect(fetchMock.mock.calls.length).toBe(3); // original + refresh + one retry — stop
  });

  it('parallel 401s share ONE refresh (single-flight)', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(UNAUTHORIZED())
      .mockResolvedValueOnce(UNAUTHORIZED())
      .mockResolvedValueOnce(jsonResponse(200, { access_token: 'a', refresh_token: 'r', user: { id: 1 } }))
      .mockImplementation(async () => OK());
    vi.stubGlobal('fetch', fetchMock);

    const [a, b] = await Promise.all([request<{ ok: boolean }>('/wardrobe/items'), request<{ ok: boolean }>('/stylist/history')]);
    expect(a.ok && b.ok).toBe(true);
    const refreshCalls = fetchMock.mock.calls.filter((c) => String(c[0]).includes('/auth/refresh'));
    expect(refreshCalls.length).toBe(1);
  });
});
