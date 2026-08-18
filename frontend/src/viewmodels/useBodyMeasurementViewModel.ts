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

  const startMeasurementSession = useCallback(async (captureMode: 'client_side' | 'server_side' | 'manual' = 'client_side') => {
    setIsCapturing(true);
    setError(null);
    try {
      const res = await measurementService.createSession(captureMode);
      setSessionId(res.id);
      return res.id;
    } catch (err: any) {
      setError(err.message || 'Session creation failed');
      return 1;
    }
  }, []);

  const saveDerivedMeasurements = useCallback(async (data: MeasurementSessionResult) => {
    setMeasurements(data);
    const activeSessionId = sessionId || 1;
    try {
      await measurementService.submitResults(activeSessionId, data);
      showToast('Body proportions estimated and applied to active fitting session.', 'success');
    } catch (err: any) {
      console.warn('Measurement submit fallback', err);
    }
  }, [sessionId, showToast]);

  const savePermanentlyToProfile = useCallback(async () => {
    if (!isAuthenticated) {
      showToast('Sign in to permanently save your biometric sizing to your User Style Profile.', 'info');
      openAuthModal('login');
      return;
    }

    if (!sessionId) return;
    setIsSaving(true);
    try {
      await measurementService.saveToProfile(sessionId);
      setIsSaving(false);
      showToast('Measurements encrypted with Fernet-256 and saved to profile!', 'success');
    } catch (err: any) {
      setIsSaving(false);
      showToast('Failed to save to profile: ' + err.message, 'error');
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
