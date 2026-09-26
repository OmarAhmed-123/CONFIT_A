import React from 'react';
import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { I18nextProvider } from 'react-i18next';

import i18n, { setAppLanguage } from '../../../i18n/i18n';
import { CameraScanModal } from '../CameraScanModal';

vi.mock('../../../privacy/usePhotoConsent', () => ({
  usePhotoConsent: () => ({
    requestConsent: vi.fn().mockResolvedValue(false),
    consentDialog: null,
  }),
}));

const canvasContext = {
  arc: vi.fn(),
  beginPath: vi.fn(),
  clearRect: vi.fn(),
  drawImage: vi.fn(),
  ellipse: vi.fn(),
  fill: vi.fn(),
  fillText: vi.fn(),
  lineTo: vi.fn(),
  moveTo: vi.fn(),
  setLineDash: vi.fn(),
  stroke: vi.fn(),
  strokeRect: vi.fn(),
  fillStyle: '',
  font: '',
  lineWidth: 1,
  strokeStyle: '',
};

function mediaDevices(getUserMedia?: () => Promise<MediaStream>) {
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: {
      enumerateDevices: vi.fn().mockResolvedValue([]),
      ...(getUserMedia ? { getUserMedia: vi.fn(getUserMedia) } : {}),
    },
  });
}

function renderModal(overrides: Partial<React.ComponentProps<typeof CameraScanModal>> = {}) {
  const props: React.ComponentProps<typeof CameraScanModal> = {
    isOpen: true,
    onClose: vi.fn(),
    onApplyMeasurements: vi.fn(),
    ...overrides,
  };
  const view = render(
    <I18nextProvider i18n={i18n}>
      <CameraScanModal {...props} />
    </I18nextProvider>,
  );
  return { ...view, props };
}

beforeEach(async () => {
  await setAppLanguage('en');
  mediaDevices();
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
    canvasContext as unknown as CanvasRenderingContext2D,
  );
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue(
    'data:image/jpeg;base64,local-camera-frame',
  );
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});

afterEach(async () => {
  cleanup();
  vi.restoreAllMocks();
  await setAppLanguage('en');
});

describe('CameraScanModal responsive and privacy contract', () => {
  it('keeps the empty state and canvas in the same bounded stage layer', () => {
    renderModal();

    const overlay = screen.getByTestId('camera-modal-overlay');
    const stage = screen.getByTestId('camera-stage');
    const canvas = screen.getByTestId('camera-preview-canvas');
    const emptyState = screen.getByTestId('camera-empty-state');

    // TryOnFitView uses space-y-10; !m-0 prevents that parent selector from
    // shifting a fixed, full-viewport dialog down by 40px.
    expect(overlay).toHaveClass('fixed', 'inset-0', '!m-0');
    expect(stage).toHaveClass('relative', 'overflow-hidden', 'min-w-0');
    expect(canvas).toHaveClass('absolute', 'inset-0', 'hidden');
    expect(emptyState).toHaveClass('absolute', 'inset-0');
    expect(stage).toContainElement(canvas);
    expect(stage).toContainElement(emptyState);
    expect(screen.getAllByRole('tab')).toHaveLength(4);
  });

  it('changes methods through real accessible tabs', () => {
    renderModal();

    const uploadTab = screen.getByRole('tab', { name: /photo upload/i });
    fireEvent.click(uploadTab);

    expect(uploadTab).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel')).toHaveAttribute('id', 'camera-scan-panel-upload');
    expect(screen.getByRole('button', { name: /choose a full-length upright photo/i })).toBeVisible();
  });

  it('shows an actionable no-camera fallback when permission is denied', async () => {
    const denial = Object.assign(new Error('denied'), { name: 'NotAllowedError' });
    mediaDevices(() => Promise.reject(denial));
    renderModal();

    fireEvent.click(screen.getByRole('button', { name: /enable camera/i }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/permission was denied/i);
    expect(screen.getByRole('button', { name: /retry camera/i })).toBeVisible();
    expect(screen.getByRole('button', { name: /use photo upload/i })).toBeVisible();
    expect(screen.getByRole('button', { name: /enter measurements/i })).toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: /enter measurements/i }));
    expect(screen.getByRole('tab', { name: /manual ruler/i })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('heading', { name: /enter your measurements/i })).toBeVisible();
  });

  it('reports an unsupported camera context instead of leaving a blank stage', async () => {
    mediaDevices();
    renderModal();

    fireEvent.click(screen.getByRole('button', { name: /enable camera/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/restricted/i);
    expect(screen.getByTestId('camera-empty-state')).toBeVisible();
  });

  it('stops a late camera stream after the user switches to a fallback', async () => {
    let resolveStream!: (stream: MediaStream) => void;
    const pending = new Promise<MediaStream>((resolve) => {
      resolveStream = resolve;
    });
    const stop = vi.fn();
    const stream = { getTracks: () => [{ stop }] } as unknown as MediaStream;
    mediaDevices(() => pending);
    renderModal();

    fireEvent.click(screen.getByRole('button', { name: /enable camera/i }));
    fireEvent.click(screen.getByRole('tab', { name: /photo upload/i }));
    await act(async () => resolveStream(stream));

    expect(stop).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('tab', { name: /photo upload/i })).toHaveAttribute('aria-selected', 'true');
  });

  it('stops active tracks and invokes close from the labelled close control', async () => {
    const stop = vi.fn();
    const stream = { getTracks: () => [{ stop }] } as unknown as MediaStream;
    mediaDevices(() => Promise.resolve(stream));
    const onClose = vi.fn();
    renderModal({ onClose });

    fireEvent.click(screen.getByRole('button', { name: /enable camera/i }));
    await screen.findByRole('button', { name: /use frame with my entered measurements/i });
    fireEvent.click(screen.getByRole('button', { name: /close size studio/i }));

    expect(stop).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('never includes the local camera frame in the applied measurement payload', async () => {
    const stop = vi.fn();
    const stream = { getTracks: () => [{ stop }] } as unknown as MediaStream;
    mediaDevices(() => Promise.resolve(stream));
    const onApplyMeasurements = vi.fn();
    renderModal({ onApplyMeasurements });

    fireEvent.click(screen.getByRole('button', { name: /enable camera/i }));
    fireEvent.click(await screen.findByRole('button', { name: /use frame with my entered measurements/i }));
    await waitFor(() => expect(screen.getByText(/your measurements & size match/i)).toBeVisible(), {
      timeout: 2500,
    });
    fireEvent.click(screen.getByRole('button', { name: /apply to sizing/i }));

    expect(onApplyMeasurements).toHaveBeenCalledTimes(1);
    expect(onApplyMeasurements.mock.calls[0][0]).not.toHaveProperty('scanned_image_url');
    expect(JSON.stringify(onApplyMeasurements.mock.calls[0][0])).not.toContain('local-camera-frame');
  });

  it('renders the complete core workflow in Arabic RTL', async () => {
    await setAppLanguage('ar');
    renderModal();

    const dialog = screen.getByRole('dialog', { name: /استوديو المقاس الذي يحفظ خصوصيتك/i });
    expect(document.documentElement).toHaveAttribute('dir', 'rtl');
    expect(dialog).toHaveAttribute('dir', 'rtl');
    expect(screen.getByRole('tab', { name: /الكاميرا المباشرة/i })).toBeVisible();
    expect(screen.getByRole('button', { name: /تشغيل الكاميرا/i })).toBeVisible();
    expect(screen.getByLabelText(/مرجع طولك/i)).toBeVisible();
  });
});
