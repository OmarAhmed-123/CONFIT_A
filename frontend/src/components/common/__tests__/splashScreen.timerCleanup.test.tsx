import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, act } from '@testing-library/react';

/**
 * SplashScreen — timer cleanup on unmount.
 *
 * Regression: the effect armed two `setTimeout`s (1100ms fade, 1500ms finish) and never
 * cleared them. In the browser that is a setState-after-unmount; in the test runner the
 * timer fires after jsdom has torn down `window`, which surfaced as an unrelated-looking
 * `ReferenceError: window is not defined` attributed to whichever suite happened to be
 * running — a flaky `frontend` required check that failed a PR touching zero TypeScript.
 *
 * These tests assert the contract directly instead of relying on teardown order:
 *  1. the two timers the component arms are the two it clears on unmount;
 *  2. advancing time after unmount neither throws nor calls onComplete;
 *  3. not unmounting early still completes exactly once (so the leak cannot be "fixed"
 *     by never firing the timers at all).
 *
 * NOTE on timer counting: the CLAIM effect writes `sessionStorage`, and jsdom implements
 * `setItem` by queuing its own storage task on `setTimeout` (delay 0). A global
 * `vi.getTimerCount()` therefore never returns to its pre-render value here. Assertions are
 * scoped to the component's own timer ids (collected by delay) rather than to the global
 * count, so jsdom's bookkeeping cannot make them pass or fail spuriously.
 *
 * The component keeps a module-level "armed" flag, so each test re-imports the module.
 */
const FADE_MS = 1100;
const FINISH_MS = 1500;

async function loadSplash() {
  vi.resetModules();
  const mod = await import('../SplashScreen');
  return mod.SplashScreen;
}

/** Timer ids created while `render` runs, keyed by the delay they were armed with. */
function collectTimerIdsByDelay(setTimeoutSpy: ReturnType<typeof vi.spyOn>) {
  const byDelay = new Map<number, unknown[]>();
  setTimeoutSpy.mock.calls.forEach((call, i) => {
    const delay = call[1] as number | undefined;
    if (typeof delay !== 'number') return;
    const id = setTimeoutSpy.mock.results[i]?.value;
    if (!byDelay.has(delay)) byDelay.set(delay, []);
    byDelay.get(delay)!.push(id);
  });
  return byDelay;
}

describe('SplashScreen — timer cleanup on unmount', () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('clears every timer it armed when it unmounts', async () => {
    const setTimeoutSpy = vi.spyOn(globalThis, 'setTimeout');
    const clearTimeoutSpy = vi.spyOn(globalThis, 'clearTimeout');

    const SplashScreen = await loadSplash();
    const { unmount } = render(<SplashScreen />);

    const byDelay = collectTimerIdsByDelay(setTimeoutSpy);
    const fadeId = byDelay.get(FADE_MS)?.[0];
    const finishId = byDelay.get(FINISH_MS)?.[0];

    // The component must actually be arming both timers — otherwise the cleanup
    // assertions below would hold vacuously for a splash that never fades or finishes.
    expect(fadeId).toBeDefined();
    expect(finishId).toBeDefined();

    const timersBeforeUnmount = vi.getTimerCount();
    unmount();

    expect(clearTimeoutSpy).toHaveBeenCalledWith(fadeId);
    expect(clearTimeoutSpy).toHaveBeenCalledWith(finishId);

    // Exactly the two component timers disappear; jsdom's own storage task (see the
    // note above) is not the component's to clear and is expected to survive.
    expect(vi.getTimerCount()).toBe(timersBeforeUnmount - 2);
  });

  it('does not call onComplete, and does not throw, when time advances after unmount', async () => {
    const SplashScreen = await loadSplash();
    const onComplete = vi.fn();
    const { unmount } = render(<SplashScreen onComplete={onComplete} />);

    unmount();

    expect(() => {
      act(() => {
        vi.advanceTimersByTime(5000);
      });
    }).not.toThrow();

    expect(onComplete).not.toHaveBeenCalled();
  });

  it('still completes normally when it is NOT unmounted early', async () => {
    // Guard against "fixing" the leak by never firing the timers at all.
    const SplashScreen = await loadSplash();
    const onComplete = vi.fn();
    render(<SplashScreen onComplete={onComplete} />);

    act(() => {
      vi.advanceTimersByTime(1600);
    });

    expect(onComplete).toHaveBeenCalledTimes(1);
  });
});
