// Pure display mapping for the sleeve-integrity gate verdicts, so the
// honesty rules are unit-testable without rendering the whole modal:
//   * no gate state / mode "off"  -> nothing is displayed (absence is never
//     turned into a claim of "verified");
//   * REFUSE verdicts can only arrive in OBSERVE mode (under enforce the
//     render fails with VTON_SLEEVES_NOT_VERIFIED and no image is delivered)
//     -> they must display as NOT VERIFIED, never as success;
//   * an uncalibrated gate reports itself as advisory (historical default
//     thresholds) — the UI must not present advisory as guarantee.
import type { SleeveGateState } from '../../models';

export interface SleeveGateDisplay {
  tone: 'verified' | 'warning';
  text: string;
}

export function sleeveGateDisplay(
  gate: SleeveGateState | null | undefined,
  opts: { verificationFailed?: boolean } = {},
): SleeveGateDisplay | null {
  if (!gate || gate.mode === 'off') return null;
  // When the layer-verification gate already failed the render, the sleeve
  // gate ran (or skipped) on a render that is itself unverified — the
  // verification chip carries that warning; stay quiet to avoid stacked
  // contradictory banners on an already-flagged preview.
  if (opts.verificationFailed) return null;
  const agg = gate.aggregate;
  if (gate.error) {
    return {
      tone: 'warning',
      text: 'Sleeve gate: the check could not run — sleeve presence is UNVERIFIED',
    };
  }
  if (!agg) return null;
  const advisorySuffix =
    gate.calibrated === false
      ? ' (advisory: gate not yet calibrated for this engine build)'
      : '';
  if (agg.layers_relevant === 0) {
    // Nothing in this outfit declared long sleeves; say nothing — silence is
    // honest here and "no long sleeves" is not a user-facing concern.
    return null;
  }
  if (agg.all_sleeves_verified) {
    return {
      tone: 'verified',
      text: `Sleeve gate: long sleeves verified present in the render${advisorySuffix}`,
    };
  }
  return {
    tone: 'warning',
    text: `Sleeve gate: ${agg.layers_refused} of ${agg.layers_relevant} long-sleeve layer(s) NOT verified — the render may be missing sleeves${advisorySuffix}`,
  };
}
