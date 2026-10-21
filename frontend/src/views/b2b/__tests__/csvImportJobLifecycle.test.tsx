import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { I18nextProvider } from 'react-i18next';
import i18n from '../../../i18n/i18n';
import { CSVProductImportModal } from '../../../components/brands/CSVProductImportModal';
import { brandService } from '../../../services/apiServices';

/**
 * THE IMPORT IS ASYNCHRONOUS NOW, SO THE UI MUST NOT PRETEND IT IS DONE.
 *
 * The endpoint returns 202 with a job id before any row is touched. That makes
 * three screens possible immediately after confirming — queued, running, and
 * dead — and the modal previously rendered all of them with a green tick and
 * "Import Operation Completed". These tests pin the honest behaviour: progress
 * comes from the job row, failure is named and offers a retry that the server
 * actually accepts, and a refusal (queue down) never reaches the result screen.
 */

const preview = {
  total_rows: 2,
  valid_rows_count: 2,
  error_rows_count: 0,
  warning_rows_count: 0,
  duplicate_rows_count: 0,
  can_import: true,
  preview_records: [
    {
      row_number: 2,
      status: 'valid',
      action: 'create',
      product_name: 'Async Coat',
      sku: 'ASYNC-001',
      category: 'tops',
      price: '850.00',
      currency: 'EGP',
      stock: 5,
      size: 'M',
      color: 'Navy',
    },
  ],
  errors: [],
  warnings: [],
};

vi.mock('../../../services/apiServices', () => ({
  brandService: {
    getStores: vi.fn().mockResolvedValue([]),
    previewCatalogCSV: vi.fn(),
    confirmCatalogImport: vi.fn(),
    getCatalogImportJob: vi.fn(),
    retryCatalogImport: vi.fn(),
    exportImportErrors: vi.fn(),
  },
}));

const renderModal = () =>
  render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>
        <CSVProductImportModal isOpen={true} onClose={vi.fn()} onSuccess={vi.fn()} />
      </MemoryRouter>
    </I18nextProvider>,
  );

const uploadAndConfirm = async () => {
  const file = new File(['product_name,sku\nAsync Coat,ASYNC-001'], 'async.csv', {
    type: 'text/csv',
  });
  const input = screen
    .getByLabelText(/Drop CSV catalog file here or click to browse/i)
    .querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [file] } });
  await waitFor(() => expect(screen.getByText(/Confirm & Import/i)).toBeInTheDocument());
  fireEvent.click(screen.getByText(/Confirm & Import/i));
};

describe('background catalog import lifecycle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (brandService.previewCatalogCSV as any).mockResolvedValue(preview);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows a queued job as in progress, not as a completed import', async () => {
    (brandService.confirmCatalogImport as any).mockResolvedValue({
      job_id: 412,
      status: 'queued',
      total_rows: 0,
      processed_rows: 0,
      accepted_rows: 0,
      rejected_rows: 0,
      duplicate_rows: 0,
      errors: [],
    });
    // The poller will be asked; hold it on "processing" so the test can look at
    // the running screen.
    (brandService.getCatalogImportJob as any).mockResolvedValue({
      job_id: 412,
      status: 'processing',
      total_rows: 240,
      processed_rows: 120,
      accepted_rows: 118,
      rejected_rows: 2,
      duplicate_rows: 0,
      errors: [],
    });

    renderModal();
    await uploadAndConfirm();

    await waitFor(() => {
      expect(brandService.getCatalogImportJob).toHaveBeenCalledWith(412);
      expect(screen.getByText(/Import In Progress/i)).toBeInTheDocument();
    }, { timeout: 6000 });
    // The lie that was removed: a completed headline over a job that has not
    // finished.
    expect(screen.queryByText(/Import Operation Completed/i)).not.toBeInTheDocument();
    expect(screen.getByText('120 / 240')).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '120');
    expect(screen.getByText(/you can close this window/i)).toBeInTheDocument();
  });

  it('stops polling and shows the final counts once the job is terminal', async () => {
    (brandService.confirmCatalogImport as any).mockResolvedValue({
      job_id: 413,
      status: 'queued',
      total_rows: 0,
      processed_rows: 0,
      accepted_rows: 0,
      rejected_rows: 0,
      duplicate_rows: 0,
      errors: [],
    });
    (brandService.getCatalogImportJob as any).mockResolvedValue({
      job_id: 413,
      status: 'partially_completed',
      total_rows: 240,
      processed_rows: 240,
      accepted_rows: 237,
      rejected_rows: 3,
      duplicate_rows: 0,
      errors: [{ row: 9, field: 'base_price', message: 'Price must be positive' }],
    });

    renderModal();
    await uploadAndConfirm();

    await waitFor(() => {
      expect(screen.getByText(/Import Operation Completed/i)).toBeInTheDocument();
    }, { timeout: 6000 });
    const calls = (brandService.getCatalogImportJob as any).mock.calls.length;
    expect(calls).toBeGreaterThan(0);
    // A terminal job must not be polled again: wait past one interval.
    await new Promise((resolve) => setTimeout(resolve, 120));
    expect((brandService.getCatalogImportJob as any).mock.calls.length).toBe(calls);
  });

  it('names the failure and offers the retry the API accepts', async () => {
    (brandService.confirmCatalogImport as any).mockResolvedValue({
      job_id: 414,
      status: 'queued',
      total_rows: 0,
      processed_rows: 0,
      accepted_rows: 0,
      rejected_rows: 0,
      duplicate_rows: 0,
      errors: [],
    });
    (brandService.getCatalogImportJob as any).mockResolvedValue({
      job_id: 414,
      status: 'failed',
      total_rows: 240,
      processed_rows: 31,
      accepted_rows: 31,
      rejected_rows: 0,
      duplicate_rows: 0,
      attempts: 3,
      last_error: 'worker_lost: heartbeat expired',
      errors: [],
    });
    (brandService.retryCatalogImport as any).mockResolvedValue({
      job_id: 414,
      status: 'queued',
      total_rows: 240,
      processed_rows: 0,
      accepted_rows: 0,
      rejected_rows: 0,
      duplicate_rows: 0,
      errors: [],
    });

    renderModal();
    await uploadAndConfirm();

    await waitFor(() => {
      expect(screen.getByText(/Import Did Not Finish/i)).toBeInTheDocument();
      expect(screen.getByText(/worker_lost: heartbeat expired/i)).toBeInTheDocument();
    }, { timeout: 6000 });
    expect(screen.queryByText(/Import Operation Completed/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByText(/Retry this import/i));
    await waitFor(() => {
      expect(brandService.retryCatalogImport).toHaveBeenCalledWith(414);
    });
    // Back to a running screen: the retried job re-enters the poller.
    await waitFor(() => {
      expect(screen.getByText(/Import In Progress/i)).toBeInTheDocument();
    }, { timeout: 6000 });
  });

  it('a refused job never reaches the result screen', async () => {
    (brandService.confirmCatalogImport as any).mockRejectedValue(
      new Error('The import queue is unavailable, so nothing was imported.'),
    );

    renderModal();
    await uploadAndConfirm();

    await waitFor(() => {
      expect(
        screen.getByText(/The import queue is unavailable, so nothing was imported/i),
      ).toBeInTheDocument();
    });
    expect(screen.queryByText(/Import Operation Completed/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Import Did Not Finish/i)).not.toBeInTheDocument();
    // No job exists, so nothing may be polled.
    expect(brandService.getCatalogImportJob).not.toHaveBeenCalled();
  });
});
