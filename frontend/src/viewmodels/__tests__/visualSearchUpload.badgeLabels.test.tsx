/**
 * SEARCH-01 upload path + FitScoreBadge honesty labels.
 *
 * 1) runVisualSearch must route an UPLOADED photo (data URL) to the SAME real
 *    endpoint as sample/URL searches — POST /tryon/visual-search via
 *    tryOnService.searchVisual({ image_base64 }) — and a URL source must map
 *    to image_url. Before the audit fix the modal had NO upload path at all
 *    (samples + URL only), so users could never search with their own photo.
 *
 * 2) FitScoreBadge must render the caller's label verbatim: catalog
 *    compatibility numbers are "Match"/"Style Match", scan confidence is
 *    "Confidence" — the catch-all "% Fit" presentation was the audit's
 *    "92% Fit" honesty complaint.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { render, screen } from '@testing-library/react';

const mocks = vi.hoisted(() => ({
  searchVisual: vi.fn(),
  showToast: vi.fn(),
}));

vi.mock('../../services/apiServices', () => ({
  tryOnService: { searchVisual: mocks.searchVisual },
}));
vi.mock('../../stores/uiStore', () => ({
  useUIStore: () => ({ showToast: mocks.showToast }),
}));

import { useTryOnViewModel } from '../useTryOnViewModel';
import { FitScoreBadge } from '../../components/common/CommonComponents';

describe('runVisualSearch source routing (upload vs URL)', () => {
  beforeEach(() => {
    mocks.searchVisual.mockReset();
    mocks.searchVisual.mockResolvedValue({ results_count: 0, matches: [] });
    mocks.showToast.mockReset();
  });

  it('routes an uploaded data URL through image_base64', async () => {
    const { result } = renderHook(() => useTryOnViewModel());
    const dataUrl = 'data:image/jpeg;base64,/9j/4AAQSkZJRg==';
    await act(async () => {
      await result.current.runVisualSearch({ imageBase64: dataUrl });
    });
    await waitFor(() => {
      expect(mocks.searchVisual).toHaveBeenCalledTimes(1);
    });
    expect(mocks.searchVisual).toHaveBeenCalledWith({
      image_url: undefined,
      image_base64: dataUrl,
    });
    expect(result.current.visualSearchError).toBeNull();
  });

  it('routes a URL source through image_url (samples & pasted links)', async () => {
    const { result } = renderHook(() => useTryOnViewModel());
    await act(async () => {
      await result.current.runVisualSearch('https://img.example/coat.jpg');
    });
    expect(mocks.searchVisual).toHaveBeenCalledWith({
      image_url: 'https://img.example/coat.jpg',
      image_base64: undefined,
    });
  });

  it('surfaces an honest error terminal state on failure', async () => {
    mocks.searchVisual.mockRejectedValueOnce({ message: 'boom' });
    const { result } = renderHook(() => useTryOnViewModel());
    await act(async () => {
      await result.current.runVisualSearch({ imageBase64: 'data:image/png;base64,AAA' });
    });
    await waitFor(() => {
      expect(result.current.visualSearchError).toBe('boom');
    });
    expect(mocks.showToast).toHaveBeenCalled();
  });
});

describe('FitScoreBadge honesty labels', () => {
  it('renders the explicit label instead of a hardcoded "% Fit"', () => {
    render(<FitScoreBadge score={92} label="Style Match" verdict="catalog heuristic — not a drape fit" />);
    expect(screen.getByText(/92% Style Match/)).toBeTruthy();
    expect(screen.queryByText(/92% Fit/)).toBeNull();
    expect(screen.getByText(/catalog heuristic/)).toBeTruthy();
  });

  it('defaults to Fit only where a real fit claim exists', () => {
    render(<FitScoreBadge score={88} verdict="Recommended M" />);
    expect(screen.getByText(/88% Fit/)).toBeTruthy();
  });

  it('renders confidence labels for scan results', () => {
    render(<FitScoreBadge score={95} label="Confidence" verdict="calibrated body scan" />);
    expect(screen.getByText(/95% Confidence/)).toBeTruthy();
  });

  it('renders nothing without a score', () => {
    const { container } = render(<FitScoreBadge score={null} />);
    expect(container.textContent).toBe('');
  });
});
