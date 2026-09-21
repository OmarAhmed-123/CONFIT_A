import { msg, detail } from '../i18n/messages';
import { useState, useCallback } from 'react';
import { measurementService, MeasurementSessionResult } from '../services/measurementService';
import { useAuthStore } from '../stores/authStore';
import { useUIStore } from '../stores/uiStore';

export function useBodyMeasurementViewModel() {
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [isCapturing, setIsCapturing] = useState(false);
  const [measurements, setMeasurements] = useState<MeasurementSessionResult | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { isAuthenticated } = useAuthStore();
  const { showToast, openAuthModal } = useUIStore();

  /**
   * Start a measurement session.
   *
   * `consentGranted` must reflect a real user action — it is passed in, never
   * assumed. On failure this returns null: the previous version returned the
   * literal id `1`, so a failed session silently wrote the caller's body
   * measurements into somebody else's session id.
   */
  const startMeasurementSession = useCallback(async (
    captureMode: 'client_side' | 'server_side' | 'manual' = 'client_side',
    consentGranted = false,
  ) => {
    setIsCapturing(true);
    setError(null);
    try {
      const res = await measurementService.createSession(captureMode, { consentGranted });
      setSessionId(res.id);
      return res.id;
    } catch (err: any) {
      setError(err.message || 'Session creation failed');
      return null;
    } finally {
      setIsCapturing(false);
    }
  }, []);

  const saveDerivedMeasurements = useCallback(async (data: MeasurementSessionResult) => {
    setMeasurements(data);
    if (!sessionId) {
      // No session => nothing to attach the results to. Reporting success here
      // (as the `sessionId || 1` fallback effectively did) told the user their
      // measurements were saved when they were not.
      setError('No active measurement session — start one before submitting results.');
      showToast(msg('toast.measurements_no_session'), 'error');
      return false;
    }
    try {
      await measurementService.submitResults(sessionId, data);
      showToast(msg('toast.measurements_saved_session'), 'success');
      return true;
    } catch (err: any) {
      setError(err?.message || 'Could not submit measurements');
      showToast(msg('toast.measurements_save_failed', { reason: detail(err) }), 'error');
      return false;
    }
  }, [sessionId, showToast]);

  const savePermanentlyToProfile = useCallback(async () => {
    if (!isAuthenticated) {
      showToast(msg('toast.measurements_signin_to_save'), 'info');
      openAuthModal('login');
      return;
    }

    if (!sessionId) return;
    setIsSaving(true);
    try {
      await measurementService.saveToProfile(sessionId);
      setIsSaving(false);
      showToast(msg('toast.measurements_saved_encrypted'), 'success');
    } catch (err: any) {
      setIsSaving(false);
      showToast(msg('toast.measurements_profile_failed', { reason: detail(err) }), 'error');
    }
  }, [isAuthenticated, sessionId, showToast, openAuthModal]);

  return {
    sessionId,
    isCapturing,
    measurements,
    isSaving,
    error,
    startMeasurementSession,
    saveDerivedMeasurements,
    savePermanentlyToProfile,
  };
}
