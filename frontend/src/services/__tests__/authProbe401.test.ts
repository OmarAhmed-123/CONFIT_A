import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

/**
 * Bootstrap 401s must be silent — measured on the live store 2026-10-20.
 *
 * With a stale `confit_csrf` cookie (a real state: the user signed out in
 * another tab, or the httpOnly session cookie expired while the readable one
 * lingered) every guest page load did this:
 *
 *   GET  /api/v1/auth/me      → 401
 *   POST /api/v1/auth/refresh → 401      (guaranteed — there is no refresh cookie)
 *   window 'confit:session-expired' → authStore opens the LOGIN MODAL
 *
 * The modal is the actual harm: `authStore.ts` subscribes to that event and
 * calls `openAuthModal('login')`, so a visitor who never signed in gets a login
 * prompt thrown in their face, plus two red console errors.
 *
 * The fix keeps one honest 401 (the server is right: there is no session) and
 * removes the escalation.
 */

type Call = { url: string; method: string };

function jsonResponse(status: number, body: unknown = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

describe('apiClient — bootstrap auth probe', () => {
  let calls: Call[];
  let dispatched: string[];
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.resetModules();
    calls = [];
    dispatched = [];
    localStorage.clear();

    fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method || 'GET').toUpperCase();
      calls.push({ url, method });
      if (url.includes('/auth/refresh')) return jsonResponse(401, { error: { code: 'UNAUTHENTICATED' } });
      if (url.includes('/auth/me')) return jsonResponse(401, { error: { code: 'UNAUTHENTICATED' } });
      if (url.includes('/cart')) return jsonResponse(401, { error: { code: 'UNAUTHENTICATED' } });
      return jsonResponse(200, {});
    });
    vi.stubGlobal('fetch', fetchMock);

    const original = window.dispatchEvent.bind(window);
    vi.spyOn(window, 'dispatchEvent').mockImplementation((event: Event) => {
      dispatched.push(event.type);
      return original(event);
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it('does not spend a doomed refresh and does not fire session-expired for a guest', async () => {
    const { request } = await import('../apiClient');

    await expect(request('/auth/me', { authProbe: true })).rejects.toMatchObject({ status: 401 });

    expect(calls.map((c) => `${c.method} ${new URL(c.url, 'http://x').pathname}`)).toEqual([
      'GET /api/v1/auth/me',
    ]);
    expect(calls.some((c) => c.url.includes('/auth/refresh'))).toBe(false);
    expect(dispatched).not.toContain('confit:session-expired');
  });

  it('still attempts one refresh when a cached profile suggests a real session', async () => {
    localStorage.setItem('confit_user', JSON.stringify({ id: 1, email: 'a@b.c' }));
    const { request } = await import('../apiClient');

    await expect(request('/auth/me', { authProbe: true })).rejects.toMatchObject({ status: 401 });

    // Cached evidence buys exactly ONE renewal attempt. It fails (there is no
    // refresh cookie), so the probe fails once and the caller sets guest state.
    expect(calls.filter((c) => c.url.includes('/auth/refresh')).length).toBe(1);
    expect(calls.filter((c) => c.url.includes('/auth/me')).length).toBe(1);
    expect(dispatched).not.toContain('confit:session-expired');
  });

  it('mid-session 401s still renew and still announce expiry', async () => {
    const { request } = await import('../apiClient');

    await expect(request('/cart')).rejects.toMatchObject({ status: 401 });

    expect(calls.some((c) => c.url.includes('/auth/refresh'))).toBe(true);
    expect(dispatched).toContain('confit:session-expired');
  });
});
