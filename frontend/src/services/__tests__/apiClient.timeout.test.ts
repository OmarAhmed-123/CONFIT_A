import { describe, it, expect } from 'vitest';
import { timeoutForEndpoint } from '../apiClient';

/**
 * A single 30s ceiling on every request aborted virtual try-on renders.
 *
 * A measured single-layer render is ~22s and a multi-garment outfit applies
 * one diffusion pass PER LAYER, so a two-piece look needs ~40s before queue
 * time. The client gave up at 30s and showed "The request timed out. Please
 * try again." — which reads as a backend failure while the server was still
 * working and Vercel allows the function 300s.
 */
describe('per-endpoint request timeouts', () => {
  it('ordinary endpoints keep the 30s default', () => {
    expect(timeoutForEndpoint('/catalog/products')).toBe(30_000);
    expect(timeoutForEndpoint('/commerce/cart')).toBe(30_000);
  });

  it('multi-layer renders get long enough for one pass per garment', () => {
    expect(timeoutForEndpoint('/tryon/multi-render')).toBeGreaterThanOrEqual(120_000);
    expect(timeoutForEndpoint('/tryon/animation-render')).toBeGreaterThanOrEqual(120_000);
  });

  it('a single render gets more than the measured ~22s, with headroom', () => {
    expect(timeoutForEndpoint('/tryon/render')).toBeGreaterThan(60_000);
  });

  it('no client budget exceeds the 300s server ceiling', () => {
    for (const ep of ['/tryon/multi-render', '/tryon/animation-render',
                      '/tryon/render', '/try-on/jobs', '/tryon/visual-search']) {
      expect(timeoutForEndpoint(ep), `${ep} would outlive the function`)
        .toBeLessThan(300_000);
    }
  });

  it('the longest matching prefix wins', () => {
    // '/tryon/render' must not be shadowed by a shorter, slower-budget match.
    expect(timeoutForEndpoint('/tryon/render')).toBe(150_000);
    expect(timeoutForEndpoint('/tryon/multi-render')).toBe(240_000);
  });
});
