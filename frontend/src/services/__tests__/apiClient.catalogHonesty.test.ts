/**
 * N-1 catalog-fallback removal contract.
 *
 * Before this fix, request() routed ANY /catalog/* failure — HTTP error,
 * static-hosting 404/405, network drop — into a hardcoded client-side
 * catalogue (FALLBACK_PRODUCTS/CATEGORIES/BRANDS): a dead backend rendered
 * as a fully stocked store with fabricated ratings, stock and style scores.
 *
 * The contract now: catalogue failures throw the real ApiError and NEVER
 * resolve with fabricated payloads. These tests fail if a fallback is ever
 * reintroduced (they assert rejection where the old code returned data).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { request, ApiError } from '../apiClient';

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('request(): catalog failures are honest (no fabricated fallback)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('HTTP 500 on /catalog/products rejects with the server error — resolves to NO array', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      jsonResponse(500, { error: { code: 'DB_DOWN', message: 'catalog storage unavailable', details: {} } })
    ));
    const outcome = await request('/catalog/products').then(
      (data) => ({ fabricated: true, data }),
      (e) => ({ fabricated: false, err: e })
    );
    expect(outcome.fabricated).toBe(false);
    const err = (outcome as any).err as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe('DB_DOWN');
    expect(err.message).toBe('catalog storage unavailable');
    expect(err.status).toBe(500);
  });

  it('network drop on /catalog/products rejects with NETWORK_ERROR — no fallback catalogue', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new TypeError('Failed to fetch');
    }));
    const err = (await request('/catalog/products').catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe('NETWORK_ERROR');
    expect(err.status).toBe(0);
  });

  it('static-hosting HTML (200 non-JSON) rejects with API_NOT_REACHABLE', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response('<!doctype html><html><body>app</body></html>', {
        status: 200,
        headers: { 'Content-Type': 'text/html' },
      })
    ));
    const err = (await request('/catalog/products').catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe('API_NOT_REACHABLE');
  });

  it('404 on a product detail rejects with HTTP_ERROR/404 — never a fabricated product', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(404, { error: { code: 'NOT_FOUND', message: 'no such product', details: {} } })));
    const outcome = await request('/catalog/products/does-not-exist').then(
      (data) => ({ fabricated: true, data }),
      (e) => ({ fabricated: false, err: e })
    );
    expect(outcome.fabricated).toBe(false);
    expect(((outcome as any).err as ApiError).status).toBe(404);
  });

  it('timeout abort maps to REQUEST_TIMEOUT (distinct from connection failure)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => {
      const e = new Error('The operation was aborted.');
      e.name = 'AbortError';
      throw e;
    }));
    const err = (await request('/catalog/products').catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe('REQUEST_TIMEOUT');
  });

  it('control: a healthy 200 JSON catalog response still parses normally', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      jsonResponse(200, [{ id: 1, title: 'Real product from the API', slug: 'real-product' }])
    ));
    const data = (await request('/catalog/products')) as any[];
    expect(Array.isArray(data)).toBe(true);
    expect(data[0].title).toBe('Real product from the API');
  });
});
