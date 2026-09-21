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

  applyToTryOn: (tryOnSessionId: number, measurements: MeasurementSessionResult) =>
    request<{ session_id: number; status: string; scaling_factor: number }>(
      `/try-on/sessions/${tryOnSessionId}/apply-measurements`,
      {
        method: 'POST',
        body: JSON.stringify(measurements),
      }
    ),
};
