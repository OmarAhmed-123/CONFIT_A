/**
 * Audit round-2 R9 contract: a failed AUTH ATTEMPT must surface the
 * server's own message ("Invalid email or password."), while 401s on other
 * endpoints keep the friendly sign-in nudge (session missing/expired).
 *
 * Before the fix, request() rewrote EVERY 401 into the nudge, so a wrong
 * password told the user to "sign in" with no error at all.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { request, ApiError } from '../apiClient';

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('request() 401 message routing', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('auth attempt: keeps the server message (Invalid email or password.)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      jsonResponse(401, { error: { code: 'AUTH_FAILED', message: 'Invalid email or password.', details: {} } })
    ));
    const err = (await request('/auth/login', { method: 'POST', body: JSON.stringify({ email: 'a@b.c', password: 'x' }) })
      .catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.message).toBe('Invalid email or password.');
    expect(err.code).toBe('AUTH_FAILED');
  });

  it('other endpoints: keep the friendly sign-in nudge on 401', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      jsonResponse(401, { error: { code: 'AUTH_REQUIRED', message: 'Not authenticated', details: {} } })
    ));
    const err = (await request('/outfits').catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.message).toBe('Sign in to access your personal style profile and account features.');
  });

  it('register attempt also keeps the server message', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      jsonResponse(401, { error: { code: 'AUTH_FAILED', message: 'Email already registered.', details: {} } })
    ));
    const err = (await request('/auth/register', { method: 'POST', body: JSON.stringify({}) }).catch((e) => e)) as ApiError;
    expect(err.message).toBe('Email already registered.');
  });
});
