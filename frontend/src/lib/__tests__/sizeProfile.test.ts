/**
 * Honesty contract for the self-reported size-profile confidence model.
 *
 * The camera-scan "size studio" previously hardcoded confidence 97/94/95
 * regardless of input. The model must derive confidence from what the user
 * ACTUALLY provided, must cap self-reported grades below measured-grade
 * (95%), and must flag low-information profiles as estimates.
 */
import { describe, it, expect } from 'vitest';
import { computeSizeProfileConfidence } from '../sizeProfile';

describe('computeSizeProfileConfidence', () => {
  it('defaults-only profile (height known, nothing set) = 40% and estimated', () => {
    const r = computeSizeProfileConfidence({ provided: [] });
    expect(r.confidence).toBe(40);
    expect(r.is_estimated).toBe(true);
    expect(r.disclosure).toMatch(/limited inputs/i);
    expect(r.inputs_counted).toEqual(['height']);
  });

  it('each extra user-set input adds 15%', () => {
    const one = computeSizeProfileConfidence({ provided: ['shoulder'] });
    expect(one.confidence).toBe(55);
    const two = computeSizeProfileConfidence({ provided: ['shoulder', 'chest'] });
    expect(two.confidence).toBe(70);
    expect(two.is_estimated).toBe(false);
    const three = computeSizeProfileConfidence({ provided: ['shoulder', 'chest', 'waist'] });
    expect(three.confidence).toBe(85);
  });

  it('self-reported values never reach measured-grade 95%', () => {
    const r = computeSizeProfileConfidence({
      provided: ['shoulder', 'chest', 'waist', 'hip', 'body_shape'],
    });
    expect(r.confidence).toBeLessThanOrEqual(85);
  });

  it('preset silhouettes cap at 80%', () => {
    const r = computeSizeProfileConfidence({
      provided: ['shoulder', 'chest', 'waist', 'hip', 'body_shape'],
      preset: true,
    });
    expect(r.confidence).toBe(80);
    expect(r.disclosure).toMatch(/preset silhouette/i);
  });

  it('duplicate keys do not inflate confidence', () => {
    const r = computeSizeProfileConfidence({ provided: ['chest', 'chest', 'chest'] });
    expect(r.confidence).toBe(55);
  });
});
