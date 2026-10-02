/**
 * Feature 05 — PhotoEstimatePanel client-contract tests.
 *
 * Pins the client half of the honesty contract:
 *
 *  1. Consent is never assumed: the estimate button stays disabled until the
 *     photo AND the explicit consent checkbox are both in place, and ticking
 *     the box grants the durable `body_scan` consent-store record.
 *  2. The estimate runs against a freshly created server_side session with
 *     consentGranted: true — the session is the audit unit.
 *  3. Success renders the truth: kept measurements with values, waist as
 *     "not estimated" (never invented), the excluded list with its count,
 *     and the ±2-3 cm accuracy note. Applying is a separate user action
 *     that hands metric centimetres to the parent exactly once.
 *  4. A 422 shows the worker's actionable guidance verbatim — it is a
 *     retake instruction, not a generic failure.
 *  5. Infra failures (503) show a retryable error and fabricate nothing.
 *  6. Invalid files (wrong type / oversize) are refused before any session
 *     is created.
 */
import React from 'react';
import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { I18nextProvider } from 'react-i18next';

import i18n from '../../../i18n/i18n';
import { useConsentStore } from '../../../privacy/consentStore';

const { createSessionMock, estimateMock, toastMock } = vi.hoisted(() => ({
  createSessionMock: vi.fn(),
  estimateMock: vi.fn(),
  toastMock: vi.fn(),
}));

vi.mock('../../../services/measurementService', () => ({
  measurementService: {
    createSession: (...a: unknown[]) => createSessionMock(...a),
    estimateFromPhoto: (...a: unknown[]) => estimateMock(...a),
  },
}));
vi.mock('../../../stores/uiStore', () => {
  const store = { showToast: toastMock };
  const useUIStore = Object.assign((sel?: (s: unknown) => unknown) => (sel ? sel(store) : store), {
    getState: () => store,
    setState: vi.fn(),
  });
  return { useUIStore };
});

import { PhotoEstimatePanel } from '../PhotoEstimatePanel';

const GOOD_RESULT = {
  status: 'completed',
  sex: 'male',
  quality: 'partial',
  measurements: [
    { name: 'Chest Circumference (mm)', value_mm: 774.7, value_cm: 77.5, source: 'model' },
    { name: 'Stature', value_mm: 1760.1, value_cm: 176.0, source: 'direct_geometry' },
  ],
  measurement_count: 2,
  excluded: [
    { name: 'Hip Circumference, Maximum (mm)', value_mm: 633.2, reason: 'outside_anatomical_range' },
    { name: 'Arm Length (Shoulder to Wrist)', value_mm: 589.8, reason: 'inconsistent_with_observed_geometry' },
  ],
  excluded_count: 2,
  measurement_method: 'ai_estimate',
  accuracy_note: '±2-3 cm',
  disclaimer: 'AI-estimated measurements are approximate (±2-3 cm).',
  result_id: 20,
  session_id: 31,
  confidence_score: 60,
  source: 'ai_photo_estimate',
  stored_measurements: {
    height_cm: 176.0,
    shoulder_width_cm: null,
    chest_cm: 77.5,
    waist_cm: null,
    hip_cm: null,
    inseam_cm: 88.9,
  },
  model: { name: 'Landmarks2Anthropometry', license: 'unlicensed-research-only', commercial: false },
};

function makeFile(name = 'body.jpg', type = 'image/jpeg', size = 1024) {
  return new File([new Uint8Array(size)], name, { type });
}

function renderPanel(overrides: Partial<React.ComponentProps<typeof PhotoEstimatePanel>> = {}) {
  const props: React.ComponentProps<typeof PhotoEstimatePanel> = {
    onApply: vi.fn(),
    defaultHeightCm: null,
    defaultSex: null,
    ...overrides,
  };
  const view = render(
    <I18nextProvider i18n={i18n}>
      <PhotoEstimatePanel {...props} />
    </I18nextProvider>,
  );
  return { ...view, props };
}

function open() {
  fireEvent.click(screen.getByRole('button', { name: /estimate from a photo/i }));
}

function chooseFile(file: File) {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  // jsdom does not build FileList from fireEvent.change — assign it directly.
  Object.defineProperty(input, 'files', { value: [file], configurable: true });
  fireEvent.change(input);
}

function tickConsent() {
  fireEvent.click(screen.getByRole('checkbox'));
}

async function submit() {
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: /estimate my measurements/i }));
  });
}

describe('PhotoEstimatePanel — honesty contract', () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    useConsentStore.setState({
      grants: {},
      // Whatever shape the rest of the store has, only grants matters here.
    } as never);
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL: vi.fn(() => 'blob:mock'),
      revokeObjectURL: vi.fn(),
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('opens with the ±2–3 cm disclosure and a disabled estimate button', () => {
    renderPanel();
    open();
    // The ±2–3 cm disclosure appears in BOTH the intro and the consent line —
    // the number is the contract, so it is asserted wherever it renders.
    expect(screen.getAllByText(/±2–3 cm/i).length).toBeGreaterThanOrEqual(2);
    const btn = screen.getByRole('button', { name: /estimate my measurements/i });
    expect(btn).toBeDisabled();
  });

  it('never enables the estimate without BOTH photo and explicit consent', async () => {
    renderPanel();
    open();

    chooseFile(makeFile());
    expect(screen.getByRole('button', { name: /estimate my measurements/i })).toBeDisabled();

    tickConsent();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /estimate my measurements/i })).toBeEnabled();
    });
    // The durable consent record was granted by the explicit tick.
    expect(useConsentStore.getState().hasConsent('body_scan')).toBe(true);
  });

  it('creates a consented server_side session and sends file, sex and height anchor', async () => {
    createSessionMock.mockResolvedValue({ id: 31 });
    estimateMock.mockResolvedValue(GOOD_RESULT);

    const { props } = renderPanel({ defaultHeightCm: 176 });
    open();
    chooseFile(makeFile());
    fireEvent.change(screen.getByLabelText(/your height/i), { target: { value: '176' } });
    tickConsent();
    await submit();

    expect(createSessionMock).toHaveBeenCalledTimes(1);
    expect(createSessionMock).toHaveBeenCalledWith('server_side', { consentGranted: true });
    expect(estimateMock).toHaveBeenCalledTimes(1);
    const [sessionId, file, sex, heightCm] = estimateMock.mock.calls[0];
    expect(sessionId).toBe(31);
    expect(file).toBeInstanceOf(File);
    expect(sex).toBe('male');
    expect(heightCm).toBe(176);
    void props;
  });

  it('omits the height anchor when the user left it empty', async () => {
    createSessionMock.mockResolvedValue({ id: 32 });
    estimateMock.mockResolvedValue(GOOD_RESULT);
    renderPanel({ defaultHeightCm: null });
    open();
    chooseFile(makeFile());
    tickConsent();
    await submit();
    expect(estimateMock.mock.calls[0][3]).toBeNull();
  });

  it('renders kept values, an honest "not estimated" waist, exclusions and the accuracy note', async () => {
    createSessionMock.mockResolvedValue({ id: 31 });
    estimateMock.mockResolvedValue(GOOD_RESULT);
    renderPanel();
    open();
    chooseFile(makeFile());
    tickConsent();
    await submit();

    await waitFor(() => {
      expect(screen.getByText('Estimated measurements')).toBeInTheDocument();
    });
    // kept values render as centimetres
    expect(screen.getByText('176 cm')).toBeInTheDocument();
    expect(screen.getByText('78 cm')).toBeInTheDocument(); // 77.5 rounds to 78
    // waist is honestly absent — the model set has none
    expect(screen.getAllByText(/not estimated/i).length).toBeGreaterThan(0);
    // excluded list with the real count
    expect(screen.getByText(/2 measurements were excluded/i)).toBeInTheDocument();
    // the mandatory accuracy disclosure
    expect(screen.getByText(/±2-3 cm/i)).toBeInTheDocument();
    // quality badge passes through
    expect(screen.getByText('partial')).toBeInTheDocument();
  });

  it('applies metric centimetres to the parent exactly once per estimate', async () => {
    createSessionMock.mockResolvedValue({ id: 31 });
    estimateMock.mockResolvedValue(GOOD_RESULT);
    const onApply = vi.fn();
    renderPanel({ onApply });
    open();
    chooseFile(makeFile());
    tickConsent();
    await submit();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /use these numbers/i })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole('button', { name: /use these numbers/i }));
    expect(onApply).toHaveBeenCalledTimes(1);
    expect(onApply).toHaveBeenCalledWith({
      heightCm: 176.0,
      chestCm: 77.5,
      hipCm: null,
      waistCm: null,
    });
    // double-apply is blocked
    fireEvent.click(screen.getByRole('button', { name: /applied/i }));
    expect(onApply).toHaveBeenCalledTimes(1);
  });

  it('shows a 422 refusal guidance VERBATIM — it is a retake instruction', async () => {
    createSessionMock.mockResolvedValue({ id: 33 });
    estimateMock.mockRejectedValue({
      message: 'Request failed',
      details: { error: { code: 'POSE_OUT_OF_ENVELOPE', message: 'body turned 40° from the camera — please face the camera directly' } },
    });
    renderPanel();
    open();
    chooseFile(makeFile());
    tickConsent();
    await submit();

    await waitFor(() => {
      expect(screen.getByText('The photo could not be used')).toBeInTheDocument();
    });
    expect(
      screen.getByText(/body turned 40° from the camera — please face the camera directly/i)
    ).toBeInTheDocument();
    expect(screen.getByText('POSE_OUT_OF_ENVELOPE')).toBeInTheDocument();
    // nothing was applied
    expect(screen.queryByText('Estimated measurements')).toBeNull();
  });

  it('treats infra failure as retryable and fabricates no result', async () => {
    createSessionMock.mockResolvedValue({ id: 34 });
    estimateMock.mockRejectedValue({
      message: 'Photo estimation is unavailable right now.',
      details: { error: { code: 'ANTHROPOMETRY_UNAVAILABLE' } },
    });
    renderPanel();
    open();
    chooseFile(makeFile());
    tickConsent();
    await submit();

    await waitFor(() => {
      expect(screen.getByText(/unavailable right now/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/try again/i)).toBeInTheDocument();
    expect(screen.queryByText('Estimated measurements')).toBeNull();
  });

  it.each([
    ['wrong type', makeFile('body.gif', 'image/gif')],
    ['oversize', makeFile('huge.jpg', 'image/jpeg', 16 * 1024 * 1024)],
  ])('refuses %s before creating any session', (_label, file) => {
    renderPanel();
    open();
    chooseFile(file);
    tickConsent();
    expect(createSessionMock).not.toHaveBeenCalled();
    expect(estimateMock).not.toHaveBeenCalled();
    // and the toast explains why
    expect(toastMock).toHaveBeenCalledWith(expect.any(String), 'error');
  });
});
