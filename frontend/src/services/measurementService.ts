import { request } from './apiClient';

export interface MeasurementSessionResult {
  height_cm: number;
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

export const measurementService = {
  createSession: (captureMode: 'client_side' | 'server_side' | 'manual' = 'client_side', saveToProfile = false) =>
    request<{ id: number; status: string; capture_mode: string; message: string }>('/measurements/sessions', {
      method: 'POST',
      body: JSON.stringify({ capture_mode: captureMode, consent_granted: true, save_to_profile: saveToProfile }),
    }),

  submitResults: (sessionId: number, results: MeasurementSessionResult) =>
    request<{ status: string; result_id: number; derived_measurements: any }>(`/measurements/sessions/${sessionId}/results`, {
      method: 'POST',
      body: JSON.stringify(results),
    }),

  saveToProfile: (sessionId: number) =>
    request<{ status: string; message: string }>(`/measurements/sessions/${sessionId}/save-to-profile`, {
      method: 'POST',
    }),

  applyToTryOn: (tryOnSessionId: number, measurements: MeasurementSessionResult) =>
    request<{ session_id: number; status: string; scaling_factor: number }>(`/try-on/sessions/${tryOnSessionId}/apply-measurements`, {
      method: 'POST',
      body: JSON.stringify(measurements),
    }),
};
