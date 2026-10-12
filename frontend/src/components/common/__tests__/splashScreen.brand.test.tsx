import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, act } from '@testing-library/react';

/**
 * Brand splash contract:
 *  - shows once per browser session, then never again;
 *  - white field with the official logo, no legacy navy/gold;
 *  - decorative (aria-hidden), and removes itself after ~1.5s;
 *  - calls onComplete exactly once when it finishes.
 * The module-level "armed" guard is reset per test by re-importing the module.
 */
async function loadSplash() {
  vi.resetModules();
  const mod = await import('../SplashScreen');
  return mod.SplashScreen;
}

describe('SplashScreen — brand presentation', () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders a white, decorative splash with the logo on the first load', async () => {
    const SplashScreen = await loadSplash();
    const { container } = render(<SplashScreen />);
    const root = container.firstElementChild as HTMLElement;
    expect(root).toBeTruthy();
    expect(root.getAttribute('aria-hidden')).toBe('true');
    expect(root.className).toContain('bg-white');
    expect(root.className).not.toContain('0C0E1E');
    expect(container.querySelector('svg[role="img"]')).toBeTruthy();
    expect(container.innerHTML).not.toContain('#C5A059');
    expect(container.innerHTML).not.toContain('#0C0E1E');
  });

  it('fades out at 1.1s and removes itself at 1.5s, calling onComplete once', async () => {
    const SplashScreen = await loadSplash();
    const onComplete = vi.fn();
    const { container } = render(<SplashScreen onComplete={onComplete} />);

    act(() => {
      vi.advanceTimersByTime(1100);
    });
    expect((container.firstElementChild as HTMLElement).className).toContain('opacity-0');

    act(() => {
      vi.advanceTimersByTime(400);
    });
    expect(container.firstElementChild).toBeNull();
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it('does not show again within the same session', async () => {
    sessionStorage.setItem('confit_splash_viewed', 'true');
    const SplashScreen = await loadSplash();
    const { container } = render(<SplashScreen />);
    expect(container.firstElementChild).toBeNull();
  });
});
