/**
 * Honest confidence model for self-reported size profiles.
 *
 * Mirrors the platform's documented no-photo-fit rule
 * (backend/app/services/no_photo_fit_service.py): base 40% + 15% per
 * ADDITIONAL user-provided input, capped at 95% for measured inputs.
 *
 * This module covers the CameraScan "size studio", whose inputs are
 * self-reported (sliders / presets) — NOT measured. It therefore caps
 * lower (85% manual / 80% preset) so a declared value can never present
 * itself with measured-grade confidence. Values left at slider defaults
 * count as NOT provided (defaults are not data).
 *
 * History: the modal previously hardcoded confidence 97/94/95 with fake
 * "keypoints locked" CV logs while deriving all numbers from height
 * ratios — fixed in fix/scan-honesty (audit indicator scan).
 */

export interface SizeProfileConfidence {
  confidence: number;
  is_estimated: boolean;
  disclosure: string;
  inputs_counted: string[];
}

const BASE = 40;
const STEP = 15;
const SELF_REPORTED_CAP = 85;
const PRESET_CAP = 80;

export function computeSizeProfileConfidence(args: {
  /** keys the user actually set (not left at defaults), e.g. 'shoulder', 'chest', 'waist', 'hip', 'body_shape'. 'height' is implied. */
  provided: string[];
  /** values came from a canned silhouette preset chosen by the user */
  preset?: boolean;
}): SizeProfileConfidence {
  const keys = Array.from(new Set(['height', ...args.provided]));
  const extra = keys.length - 1; // inputs beyond the always-known height
  const cap = args.preset ? PRESET_CAP : SELF_REPORTED_CAP;
  const confidence = Math.min(cap, BASE + extra * STEP);
  const is_estimated = confidence < 70;

  const disclosure = args.preset
    ? 'Based on a preset silhouette — adjust the sliders to your real measurements for a higher-confidence profile.'
    : is_estimated
      ? 'Estimated from limited inputs — enter your shoulder/chest/waist for a higher-confidence profile.'
      : 'From your self-reported measurements. Self-reported values are estimates, not clinical measurements.';

  return { confidence, is_estimated, disclosure, inputs_counted: keys };
}
