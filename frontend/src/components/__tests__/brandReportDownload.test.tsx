/**
 * Spec 12 export — BrandReportDownloadButton contract.
 *
 * The documented gap was "no export endpoint exists server-side; no export
 * UI was faked". The endpoint now exists (admin-only + audited), so this is
 * the UI side of the contract:
 *   · accessible name carries the BRAND name (§7 — never icon-only);
 *   · pending/success/error are TEXT inside aria-live=polite (§5/§7);
 *   · success happens ONLY after the server's bytes arrive (§11): the blob
 *     from the service is what lands in the anchor download;
 *   · a server refusal renders the localized failure text — no download,
 *     no fake success;
 *   · AR: labels translated; axe clean in both states.
 */
import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, act, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { axe } from 'vitest-axe';
import i18n, { setAppLanguage } from '../../i18n/i18n';

const { downloadMock } = vi.hoisted(() => ({ downloadMock: vi.fn() }));

vi.mock('../../services/apiServices', () => ({
  adminService: { downloadBrandReportPdf: (...a: unknown[]) => downloadMock(...a) },
}));

import { BrandReportDownloadButton } from '../admin/BrandReportDownloadButton';

const AXE_RULES = {
  rules: { 'color-contrast': { enabled: false }, 'target-size': { enabled: false } },
};

const renderButton = () =>
  render(
    <I18nextProvider i18n={i18n}>
      <BrandReportDownloadButton brandId={5} brandName="Alpha" />
    </I18nextProvider>,
  );

describe('BrandReportDownloadButton', () => {
  let createObjectURL: ReturnType<typeof vi.fn>;
  let revokeObjectURL: ReturnType<typeof vi.fn>;
  let anchorClicks: string[];

  beforeEach(async () => {
    cleanup();
    downloadMock.mockReset();
    await act(async () => { await setAppLanguage('en'); });
    anchorClicks = [];
    createObjectURL = vi.fn(() => 'blob:fake-url');
    revokeObjectURL = vi.fn();
    (URL as unknown as Record<string, unknown>).createObjectURL = createObjectURL;
    (URL as unknown as Record<string, unknown>).revokeObjectURL = revokeObjectURL;
    // jsdom cannot navigate: capture the download anchor's click instead.
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      anchorClicks.push(this.download);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('accessible name carries the brand name; the icon is decorative', () => {
    renderButton();
    expect(
      screen.getByRole('button', { name: 'Download the product & sales report for Alpha (PDF)' }),
    ).toBeInTheDocument();
  });

  it('success ONLY after server bytes: pending text → server filename → done text', async () => {
    let resolve!: (v: { blob: Blob; filename: string | null }) => void;
    downloadMock.mockReturnValue(new Promise((r) => { resolve = r; }));
    renderButton();

    fireEvent.click(screen.getByRole('button'));
    expect(screen.getByText('Preparing the report…')).toBeInTheDocument();
    expect(screen.getByRole('button')).toHaveAttribute('aria-busy', 'true');
    expect(anchorClicks).toHaveLength(0); // nothing downloads before the server answers

    await act(async () => {
      resolve({ blob: new Blob(['%PDF-fake']), filename: 'confit-alpha-product-sales-20261006.pdf' });
    });
    await waitFor(() => expect(screen.getByText('Report downloaded.')).toBeInTheDocument());
    // The SERVER's filename is used verbatim.
    expect(anchorClicks).toEqual(['confit-alpha-product-sales-20261006.pdf']);
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:fake-url');
    expect(downloadMock).toHaveBeenCalledWith(5);
  });

  it('a server refusal shows localized failure text and downloads NOTHING', async () => {
    downloadMock.mockRejectedValue(
      Object.assign(new Error('Access restricted to admin. Current user role: consumer'), {
        code: 'FORBIDDEN_ACCESS',
        status: 403,
      }),
    );
    renderButton();
    fireEvent.click(screen.getByRole('button'));
    // FORBIDDEN_ACCESS maps to the localized errors.forbidden copy —
    // the Arabic shell never leaks the English server string.
    await waitFor(() =>
      expect(screen.getByText(i18n.t('errors.forbidden'))).toBeInTheDocument(),
    );
    expect(anchorClicks).toHaveLength(0);
    expect(createObjectURL).not.toHaveBeenCalled();
    expect(screen.queryByText('Report downloaded.')).not.toBeInTheDocument();
  });

  it('AR shell: label and states in Arabic', async () => {
    await act(async () => { await setAppLanguage('ar'); });
    downloadMock.mockResolvedValue({ blob: new Blob(['%PDF']), filename: null });
    renderButton();
    const btn = screen.getByRole('button', {
      name: 'تحميل تقرير المنتجات والمبيعات لبراند Alpha (PDF)',
    });
    fireEvent.click(btn);
    await waitFor(() => expect(screen.getByText('تم تنزيل التقرير.')).toBeInTheDocument());
    // Header stripped by a proxy ⇒ deterministic fallback name, LTR-safe.
    expect(anchorClicks).toEqual(['confit-brand-5-report.pdf']);
    await act(async () => { await setAppLanguage('en'); });
  });

  it('axe: idle and error states clean', async () => {
    downloadMock.mockRejectedValue(new Error('boom'));
    const { container } = renderButton();
    expect((await axe(container, AXE_RULES)).violations).toEqual([]);
    fireEvent.click(screen.getByRole('button'));
    await waitFor(() => expect(screen.getByText(/boom|could not be generated/)).toBeInTheDocument());
    expect((await axe(container, AXE_RULES)).violations).toEqual([]);
  });
});
