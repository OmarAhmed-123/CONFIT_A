import { request } from './apiClient';

/**
 * Measurement-session client.
 *
 * Contract notes (2026-09-21 Fit Finder remediation):
 * * Values are sent in the unit system named by `units`; the server converts
 *   once and rejects an implausible value with 422 rather than storing it.
 * * `consent_granted` is NOT hardcoded any more. Consent belongs to an
 *   explicit user action, and a session created without it cannot accumulate
 *   measurements (the server answers 403). Passing `true` from a code path
 *   with no consent UI was the client half of a consent-fabrication bug.
 * * `confidence_score` must state what the caller actually knows. It is no
 *   longer defaulted to a high value on either side of the wire.
 */
export interface MeasurementSessionResult {
  units?: 'metric' | 'imperial';
  height_cm?: number;
  height?: number;
  shoulder_width_cm?: number;
  chest_cm?: number;
  waist_cm?: number;
  hip_cm?: number;
  inseam_cm?: number;
  body_shape?: string;
  confidence_score: number;
  calibration_method?: string;
  source?: string;
}

export interface MeasurementSession {
  id: number;
  status: string;
  capture_mode: string;
  session_token?: string | null;
  message: string;
}

export interface SaveToProfileResult {
  status: string;
  session_id: number;
  result_id: number;
  /** Field NAMES only — values are encrypted at rest and never echoed back. */
  saved_fields: string[];
  message: string;
}

/**
 * Feature 05 — server-side photo estimation (Landmarks2Anthropometry worker).
 *
 * The response is the worker's honest contract, passed through verbatim:
 * per-measurement provenance (`model` vs `direct_geometry`), a transparent
 * `excluded` list with machine-readable reasons, the mandatory ±2-3 cm
 * accuracy note, and quality full | partial | geometry_only. Anything the
 * model set does not produce (shoulder, waist) is simply absent — the UI
 * must render that absence, never paper over it.
 */
export interface PhotoEstimateMeasurement {
  name: string;
  value_mm: number;
  value_cm: number;
  source: 'model' | 'direct_geometry';
}

export interface PhotoEstimateExcluded {
  name: string;
  value_mm: number;
  reason: string;
}

export interface PhotoEstimateResult {
  status: 'completed';
  sex: 'male' | 'female';
  quality: 'full' | 'partial' | 'geometry_only';
  measurements: PhotoEstimateMeasurement[];
  measurement_count: number;
  excluded: PhotoEstimateExcluded[];
  excluded_count: number;
  measurement_method: 'ai_estimate';
  accuracy_note: string;
  disclaimer: string;
  result_id: number;
  session_id: number;
  confidence_score: number;
  source: string;
  stored_measurements: {
    height_cm: number | null;
    shoulder_width_cm: number | null;
    chest_cm: number | null;
    waist_cm: number | null;
    hip_cm: number | null;
    inseam_cm: number | null;
  };
  model: {
    name: string;
    license: string;
    commercial: boolean;
    [k: string]: unknown;
  };
  [k: string]: unknown;
}

export const measurementService = {
  createSession: (
    captureMode: 'client_side' | 'server_side' | 'manual' = 'client_side',
    options: { consentGranted: boolean; saveToProfile?: boolean }
  ) =>
    request<MeasurementSession>('/measurements/sessions', {
      method: 'POST',
      body: JSON.stringify({
        capture_mode: captureMode,
        consent_granted: options.consentGranted,
        save_to_profile: options.saveToProfile ?? false,
      }),
    }),

  getSession: (sessionId: number) =>
    request<{
      id: number;
      status: string;
      capture_mode: string;
      consent_granted: boolean;
      save_to_profile: boolean;
      results: Array<Record<string, unknown>>;
      created_at: string;
    }>(`/measurements/sessions/${sessionId}`),

  submitResults: (sessionId: number, results: MeasurementSessionResult) =>
    request<{
      status: string;
      result_id: number;
      stored_measurements: Record<string, unknown>;
    }>(`/measurements/sessions/${sessionId}/results`, {
      method: 'POST',
      body: JSON.stringify(results),
    }),

  saveToProfile: (sessionId: number) =>
    request<SaveToProfileResult>(`/measurements/sessions/${sessionId}/save-to-profile`, {
      method: 'POST',
    }),

  /**
   * Feature 05 — estimate measurements from one full-body photo.
   *
   * The photo is sent to the session's server-side estimator. The call can
   * take a few seconds (real CPU inference on Modal) — callers must show a
   * busy state. A 422 response is an HONEST refusal (bad pose, no person,
   * implausible geometry): its guidance is meant to be shown to the user,
   * not swallowed.
   */
  estimateFromPhoto: (
    sessionId: number,
    file: File,
    sex: 'male' | 'female',
    heightCm?: number | null
  ) => {
    const form = new FormData();
    form.append('file', file);
    form.append('sex', sex);
    if (heightCm != null && Number.isFinite(heightCm) && heightCm > 0) {
      form.append('height_cm', String(Math.round(heightCm * 10) / 10));
    }
    return request<PhotoEstimateResult>(`/measurements/sessions/${sessionId}/photo-estimate`, {
      method: 'POST',
      body: form,
    });
  },

  applyToTryOn: (tryOnSessionId: number, measurements: MeasurementSessionResult) =>
    request<{ session_id: number; status: string; scaling_factor: number }>(
      `/try-on/sessions/${tryOnSessionId}/apply-measurements`,
      {
        method: 'POST',
        body: JSON.stringify(measurements),
      }
    ),
};
