import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, act } from '@testing-library/react';

async function loadSplash() {
  vi.resetModules();
  const mod = await import('../SplashScreen');
  return mod.SplashScreen;
}

describe('SplashScreen — accessibility (WCAG 2.2 SC 2.4.11 & reduced motion)', () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('dismisses immediately when an underlying element receives keyboard focus so focus is never obscured', async () => {
    const SplashScreen = await loadSplash();
    const onComplete = vi.fn();
    const { container } = render(
      <div>
        <SplashScreen onComplete={onComplete} />
        <a href="#confit-main-content">Skip to content</a>
      </div>
    );

    expect(container.querySelector('[role="presentation"]')).toBeTruthy();

    act(() => {
      const link = container.querySelector('a')!;
      link.focus();
    });

    expect(container.querySelector('[role="presentation"]')).toBeNull();
    expect(onComplete).toHaveBeenCalledTimes(1);

    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it('dismisses immediately on Tab or Escape keydown without duplicating onComplete', async () => {
    const SplashScreen = await loadSplash();
    const onComplete = vi.fn();
    const { container } = render(<SplashScreen onComplete={onComplete} />);

    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }));
    });

    expect(container.firstElementChild).toBeNull();
    expect(onComplete).toHaveBeenCalledTimes(1);

    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it('disables CSS opacity transitions under prefers-reduced-motion via motion-reduce:transition-none', async () => {
    const SplashScreen = await loadSplash();
    const { container } = render(<SplashScreen />);
    const root = container.firstElementChild as HTMLElement;
    expect(root.className).toContain('motion-reduce:transition-none');
  });
});
