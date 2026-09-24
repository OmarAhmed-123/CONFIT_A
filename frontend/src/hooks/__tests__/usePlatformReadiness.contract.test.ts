/** Runtime contract tests for the admin readiness source.
 *
 * TypeScript generics do not validate HTTP JSON. A 200 with malformed or
 * partial data is UNKNOWN, never READY and never a render-time crash.
 */
import { describe, expect, it } from 'vitest';
import { parsePlatformReadiness } from '../usePlatformReadiness';

const VALID = {
  status: 'healthy',
  ready: false,
  blocking_capabilities: ['virtual_try_on'],
  degraded_capabilities: ['payments'],
  unprobed_capabilities: ['ai_stylist'],
  version: '1.0.0',
};

describe('parsePlatformReadiness', () => {
  it('accepts and copies the complete /health contract', () => {
    const parsed = parsePlatformReadiness(VALID);
    expect(parsed).toEqual(VALID);
    expect(parsed.blocking_capabilities).not.toBe(VALID.blocking_capabilities);
  });

  it.each([
    null,
    'healthy',
    {},
    { ...VALID, ready: 'yes' },
    { ...VALID, blocking_capabilities: undefined },
    { ...VALID, degraded_capabilities: [42] },
    { ...VALID, unprobed_capabilities: undefined },
  ])('rejects malformed or partial response %# — caller reports UNKNOWN', (payload) => {
    expect(() => parsePlatformReadiness(payload)).toThrow(/Readiness Malformed/);
  });

  it('keeps unknown capability names verbatim instead of dropping them', () => {
    const parsed = parsePlatformReadiness({
      ...VALID,
      blocking_capabilities: ['new_capability_not_known_to_this_frontend'],
    });
    expect(parsed.blocking_capabilities).toEqual(['new_capability_not_known_to_this_frontend']);
  });
});
