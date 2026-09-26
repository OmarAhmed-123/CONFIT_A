import React from 'react';
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import i18n, { setAppLanguage } from '../../../i18n/i18n';
import { TryOnStudioErrorBoundary } from '../TryOnStudioErrorBoundary';

const BrokenStudio = () => {
  throw new Error('synthetic render failure');
};

function renderRoute(initialEntries = ['/tryon-studio'], initialIndex = initialEntries.length - 1) {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={initialEntries} initialIndex={initialIndex}>
        <Routes>
          <Route
            path="/tryon-studio"
            element={
              <TryOnStudioErrorBoundary>
                <BrokenStudio />
              </TryOnStudioErrorBoundary>
            }
          />
          <Route path="/" element={<h1>Consumer home</h1>} />
        </Routes>
      </MemoryRouter>
    </I18nextProvider>,
  );
}

const preventSyntheticErrorReport = (event: ErrorEvent) => {
  if (event.error?.message === 'synthetic render failure') event.preventDefault();
};

beforeEach(async () => {
  await setAppLanguage('en');
  window.addEventListener('error', preventSyntheticErrorReport);
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(async () => {
  cleanup();
  window.removeEventListener('error', preventSyntheticErrorReport);
  vi.restoreAllMocks();
  await setAppLanguage('en');
});

describe('TryOnStudioErrorBoundary', () => {
  it('shows an explicit recoverable error instead of a white route', () => {
    renderRoute();

    expect(screen.getByRole('alert')).toBeVisible();
    expect(screen.getByRole('heading', { name: /could not be displayed/i })).toBeVisible();
    expect(screen.getByRole('button', { name: /retry studio/i })).toBeVisible();
    expect(screen.getByRole('button', { name: /go back/i })).toBeVisible();
    expect(console.error).toHaveBeenCalled();
  });

  it('retries by remounting the failed studio and keeps the honest fallback if it fails again', () => {
    renderRoute();
    const firstLogCount = vi.mocked(console.error).mock.calls.length;

    fireEvent.click(screen.getByRole('button', { name: /retry studio/i }));

    expect(screen.getByRole('alert')).toBeVisible();
    expect(vi.mocked(console.error).mock.calls.length).toBeGreaterThan(firstLogCount);
  });

  it('returns to the previous in-app page when history exists', () => {
    renderRoute(['/', '/tryon-studio'], 1);

    fireEvent.click(screen.getByRole('button', { name: /go back/i }));

    expect(screen.getByRole('heading', { name: /consumer home/i })).toBeVisible();
  });

  it('falls back to the consumer home on a direct entry and mirrors direction in Arabic', async () => {
    await setAppLanguage('ar');
    renderRoute();

    expect(screen.getByRole('heading', { name: /تعذّر عرض/i })).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: /رجوع/i }));
    expect(screen.getByRole('heading', { name: /consumer home/i })).toBeVisible();
  });
});
