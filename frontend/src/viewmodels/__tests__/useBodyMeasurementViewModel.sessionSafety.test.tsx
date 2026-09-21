/**
 * Regression: a failed measurement session must NEVER fall back to a real id.
 *
 * Historical bug: `startMeasurementSession` returned the literal id `1` when
 * `createSession` failed, and `saveDerivedMeasurements` then submitted against
 * `sessionId || 1`. The user's body measurements were therefore written into
 * measurement session **#1 — somebody else's session**.
 *
 * The server-side owner gate is the real defence (see
 * backend/tests/test_measurement_session_security.py), but the client must not
 * be the thing attempting the cross-user write in the first place, and it must
 * not tell the user their measurements were saved when they were not.
 *
 * The brief for this closure pass explicitly says not to assume this bug is
 * fixed because a previous report claimed it. This test proves it.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';

const { createSession, submitResults, saveToProfile, showToast } = vi.hoisted(() => ({
  createSession: vi.fn(),
  submitResults: vi.fn(),
  saveToProfile: vi.fn(),
  showToast: vi.fn(),
}));

vi.mock('../../services/measurementService', () => ({
  measurementService: {
    createSession: (...a: unknown[]) => createSession(...a),
    submitResults: (...a: unknown[]) => submitResults(...a),
    saveToProfile: (...a: unknown[]) => saveToProfile(...a),
  },
}));
vi.mock('../../stores/authStore', () => ({
  useAuthStore: () => ({ isAuthenticated: true }),
}));
vi.mock('../../stores/uiStore', () => ({
  useUIStore: () => ({ showToast, openAuthModal: vi.fn() }),
}));

import { useBodyMeasurementViewModel } from '../useBodyMeasurementViewModel';

const BODY = {
  height_cm: 178,
  chest_cm: 98,
  waist_cm: 84,
  hip_cm: 99,
  body_shape: 'rectangle',
  confidence_score: 60,
  calibration_method: 'manual_entry',
};

describe('measurement session safety', () => {
  beforeEach(() => vi.clearAllMocks());

  it('returns null (never id 1) when session creation fails', async () => {
    createSession.mockRejectedValue(new Error('network down'));
    const { result } = renderHook(() => useBodyMeasurementViewModel());

    let sessionId: number | null = 999;
    await act(async () => {
      sessionId = await result.current.startMeasurementSession('manual', true);
    });

    expect(sessionId).toBeNull();
    expect(sessionId).not.toBe(1);
  });

  it('does NOT submit measurements anywhere when there is no session', async () => {
    createSession.mockRejectedValue(new Error('network down'));
    const { result } = renderHook(() => useBodyMeasurementViewModel());

    await act(async () => {
      await result.current.startMeasurementSession('manual', true);
    });
    await act(async () => {
      await result.current.saveDerivedMeasurements(BODY as never);
    });

    // The core of the bug: no write may be attempted at all.
    expect(submitResults).not.toHaveBeenCalled();
  });

  it('never reports success for a save that did not happen', async () => {
    createSession.mockRejectedValue(new Error('network down'));
    const { result } = renderHook(() => useBodyMeasurementViewModel());

    await act(async () => {
      await result.current.startMeasurementSession('manual', true);
    });
    let ok: unknown = true;
    await act(async () => {
      ok = await result.current.saveDerivedMeasurements(BODY as never);
    });

    expect(ok).toBe(false);
    const successToasts = showToast.mock.calls.filter((c) => c[1] === 'success');
    expect(successToasts).toHaveLength(0);
  });

  it('submits against the real session id when creation succeeds', async () => {
    createSession.mockResolvedValue({ id: 4242 });
    submitResults.mockResolvedValue({});
    const { result } = renderHook(() => useBodyMeasurementViewModel());

    await act(async () => {
      await result.current.startMeasurementSession('manual', true);
    });
    await act(async () => {
      await result.current.saveDerivedMeasurements(BODY as never);
    });

    expect(submitResults).toHaveBeenCalledTimes(1);
    expect(submitResults.mock.calls[0][0]).toBe(4242);
  });

  it('consent is passed through explicitly and is never assumed true', async () => {
    createSession.mockResolvedValue({ id: 7 });
    const { result } = renderHook(() => useBodyMeasurementViewModel());

    await act(async () => {
      await result.current.startMeasurementSession('manual'); // consent omitted
    });
    expect(createSession).toHaveBeenCalledWith('manual', { consentGranted: false });

    await act(async () => {
      await result.current.startMeasurementSession('manual', true);
    });
    expect(createSession).toHaveBeenLastCalledWith('manual', { consentGranted: true });
  });
});
