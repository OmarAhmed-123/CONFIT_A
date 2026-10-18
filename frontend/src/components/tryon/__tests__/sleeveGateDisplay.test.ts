/**
 * Sleeve-integrity gate chip — pure display-mapping tests.
 *
 * Honesty contract under test: absence is never turned into a claim,
 * REFUSE (observe mode) is never displayed as success, an uncalibrated
 * gate must label itself advisory, and off-mode publishes nothing.
 */
import { describe, expect, it } from 'vitest';

import { sleeveGateDisplay } from '../sleeveGateDisplay';
import type { SleeveGateState } from '../../../models';

const gate = (over: Partial<SleeveGateState> = {}): SleeveGateState => ({
  mode: 'observe',
  gate_version: 'v3.0-recovered.1',
  calibrated: true,
  threshold_source: 'manifest',
  layers: [],
  aggregate: {
    layers_relevant: 1,
    layers_verified: 1,
    layers_refused: 0,
    all_sleeves_verified: true,
  },
  ...over,
});

describe('sleeveGateDisplay', () => {
  it('renders nothing when the gate did not run or is off', () => {
    expect(sleeveGateDisplay(undefined)).toBeNull();
    expect(sleeveGateDisplay(null)).toBeNull();
    expect(sleeveGateDisplay(gate({ mode: 'off' }))).toBeNull();
  });

  it('does not stack a second warning when the verification gate already failed the render', () => {
    expect(
      sleeveGateDisplay(gate(), { verificationFailed: true }),
    ).toBeNull();
  });

  it('reports a verified render without over-claiming beyond the sleeve channel', () => {
    const d = sleeveGateDisplay(gate());
    expect(d?.tone).toBe('verified');
    expect(d?.text).toContain('long sleeves verified');
    expect(d?.text).not.toContain('advisory');
  });

  it('labels an uncalibrated gate as advisory, never as a guarantee', () => {
    const d = sleeveGateDisplay(gate({ calibrated: false, threshold_source: 'historical-defaults(unfrozen)' }));
    expect(d?.tone).toBe('verified');
    expect(d?.text).toContain('advisory');
    expect(d?.text).toContain('not yet calibrated');
  });

  it('shows a REFUSE verdict (observe mode) as NOT verified, never as success', () => {
    const d = sleeveGateDisplay(
      gate({
        aggregate: {
          layers_relevant: 2,
          layers_verified: 1,
          layers_refused: 1,
          all_sleeves_verified: false,
        },
      }),
    );
    expect(d?.tone).toBe('warning');
    expect(d?.text).toContain('1 of 2');
    expect(d?.text).toContain('NOT verified');
  });

  it('surfaces a probe that could not run as UNVERIFIED, not silence', () => {
    const d = sleeveGateDisplay(gate({ error: 'ValueError: boom', aggregate: null }));
    expect(d?.tone).toBe('warning');
    expect(d?.text).toContain('could not run');
    expect(d?.text).toContain('UNVERIFIED');
  });

  it('stays silent when nothing in the outfit declared long sleeves', () => {
    const d = sleeveGateDisplay(
      gate({
        aggregate: {
          layers_relevant: 0,
          layers_verified: 0,
          layers_refused: 0,
          all_sleeves_verified: false,
          not_applicable_layers: 3,
        },
      }),
    );
    expect(d).toBeNull();
  });
});
