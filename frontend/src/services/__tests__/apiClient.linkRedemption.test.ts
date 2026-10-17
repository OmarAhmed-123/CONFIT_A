/**
 * A bad, used, or expired email-verification link is NOT an expired session.
 *
 * The backend answers /auth/verify-email with 401 AUTH_FAILED and a specific
 * message. Before this fix the client treated that 401 like a session expiry:
 * it tried a cookie refresh and, when that failed, fired
 * 'confit:session-expired', which opened the sign-in modal over the page.
 * These tests pin the corrected behaviour: no renewal attempt, no session
 * event, and the server's own message is kept.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { request, ApiError, SESSION_EXPIRED_EVENT } from '../apiClient';

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('verify-email 401 is a link error, not a session expiry', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    localStorage.clear();
    localStorage.setItem('confit_user', '{"id":1}');
  });

  it('makes exactly one request, fires no session-expired event, keeps the server message', async () => {
    const expiredListener = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, expiredListener);
    const fetchMock = vi.fn().mockResolvedValueOnce(
      jsonResponse(401, {
        error: {
          code: 'AUTH_FAILED',
          message: 'Verification link is invalid or has already been used.',
          details: {},
        },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const err = (await request('/auth/verify-email', {
      method: 'POST',
      body: JSON.stringify({ token: 'used' }),
    }).catch((e) => e)) as ApiError;

    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe('AUTH_FAILED');
    expect(err.message).toBe('Verification link is invalid or has already been used.');
    expect(fetchMock.mock.calls.length).toBe(1); // no /auth/refresh round-trip
    expect(String(fetchMock.mock.calls[0][0])).toContain('/auth/verify-email');
    expect(expiredListener).not.toHaveBeenCalled();
    expect(localStorage.getItem('confit_user')).toBe('{"id":1}'); // session evidence untouched
    window.removeEventListener(SESSION_EXPIRED_EVENT, expiredListener);
  });
});
