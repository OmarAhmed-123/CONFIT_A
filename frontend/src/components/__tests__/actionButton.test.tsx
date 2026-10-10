/**
 * Spec 08 — Kinetic CTA with Trust State. §10 required coverage:
 *   component states · checkout error (financial controlled contract) ·
 *   try-on unavailable · keyboard/focus · reduced motion · slow API —
 *   plus §9 acceptance: CTA never disappears, no double submit, failure
 *   actionable, focus never lost, payment success only from the server.
 *
 * Structure:
 *   A. Uncontrolled machine: success / error / unavailable / unauthorized /
 *      offline / handled — labels, aria-busy, timed revert, actionability
 *   B. Trust guarantees: single-flight, focus retention (never `disabled`
 *      while pending), layout reservation (label stack + min-height),
 *      cancellation (AbortError → silent idle), slow API pending persistence
 *   C. Controlled/financial mode: checkout contract — pending from caller,
 *      NO self-painted success, error relabel actionable retry (try-on)
 *   D. Metrics: duration + outcome word only — no payload data
 *   E. axe EN + AR/RTL · reduced motion (plain button, full function)
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, act, waitFor } from '@testing-library/react';
import { axe } from 'vitest-axe';
import { I18nextProvider } from 'react-i18next';

vi.mock('../../stores/uiStore', () => {
  const openAuthModal = vi.fn();
  const useUIStore = (sel: any) => sel({ openAuthModal });
  (useUIStore as any).__openAuthModal = openAuthModal;
  return { useUIStore };
});

import i18n, { setAppLanguage } from '../../i18n/i18n';
import { ActionButton, outcomeFromResult } from '../common/ActionButton';
import { useUIStore } from '../../stores/uiStore';
import { getCtaMetrics, clearCtaMetrics } from '../../lib/ctaMetrics';

const openAuthModalMock = (useUIStore as any).__openAuthModal as ReturnType<typeof vi.fn>;

const LABELS = {
  idle: 'Save look',
  pending: 'Saving…',
  success: 'Look saved',
  error: 'Save failed — try again',
  unavailable: 'Size unavailable',
  unauthorized: 'Sign in to continue',
  offline: 'You are offline — retry',
};

const renderCta = (props: Partial<React.ComponentProps<typeof ActionButton>> = {}) =>
  render(
    <I18nextProvider i18n={i18n}>
      <ActionButton labels={LABELS} {...props} />
    </I18nextProvider>,
  );

/** The button's current visible (non-hidden) label text. */
const visibleLabel = (btn: HTMLElement) =>
  btn.querySelector('[data-testid="cta-label-stack"] > span:not(.invisible)')?.textContent;

const deferred = <T,>() => {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => ((resolve = res), (reject = rej)));
  return { promise, resolve, reject };
};

beforeEach(() => {
  clearCtaMetrics();
  openAuthModalMock.mockClear();
});
afterEach(async () => {
  cleanup();
  vi.useRealTimers();
  await setAppLanguage('en');
});

/* ------------------------------------------------------------------ */
/* A. Uncontrolled machine                                             */
/* ------------------------------------------------------------------ */
describe('ActionButton machine states', () => {
  it('success: pending (aria-busy, text) → success only after resolve → timed revert to idle', async () => {
    vi.useFakeTimers();
    const d = deferred<void>();
    renderCta({ onAction: () => d.promise });
    const btn = screen.getByRole('button');

    expect(visibleLabel(btn)).toBe('Save look');
    fireEvent.click(btn);
    expect(btn).toHaveAttribute('aria-busy', 'true');
    expect(visibleLabel(btn)).toBe('Saving…');
    // Not successful yet — the server has not answered.
    expect(btn).toHaveAttribute('data-state', 'pending');

    await act(async () => {
      d.resolve();
      await Promise.resolve();
    });
    expect(btn).toHaveAttribute('data-state', 'success');
    expect(visibleLabel(btn)).toBe('Look saved');

    act(() => void vi.advanceTimersByTime(2100));
    expect(btn).toHaveAttribute('data-state', 'idle');
    expect(visibleLabel(btn)).toBe('Save look');
  });

  it('error: rejected action → actionable error label, button still clickable (retry works)', async () => {
    let calls = 0;
    renderCta({
      onAction: async () => {
        calls += 1;
        if (calls === 1) throw new Error('server 500');
      },
    });
    const btn = screen.getByRole('button');
    await act(async () => void fireEvent.click(btn));
    expect(btn).toHaveAttribute('data-state', 'error');
    expect(visibleLabel(btn)).toBe('Save failed — try again');
    // CTA never disappears and stays actionable (§9): retry succeeds.
    await act(async () => void fireEvent.click(btn));
    expect(btn).toHaveAttribute('data-state', 'success');
    expect(calls).toBe(2);
  });

  it('try-on unavailable: outcome "unavailable" names the gap instead of a generic failure', async () => {
    renderCta({ onAction: async () => 'unavailable' as const });
    const btn = screen.getByRole('button');
    await act(async () => void fireEvent.click(btn));
    expect(btn).toHaveAttribute('data-state', 'unavailable');
    expect(visibleLabel(btn)).toBe('Size unavailable');
  });

  it('unauthorized: opens the auth modal (context kept) and says so as text', async () => {
    renderCta({ onAction: async () => { throw { status: 401 }; } });
    const btn = screen.getByRole('button');
    await act(async () => void fireEvent.click(btn));
    expect(btn).toHaveAttribute('data-state', 'unauthorized');
    expect(visibleLabel(btn)).toBe('Sign in to continue');
    expect(openAuthModalMock).toHaveBeenCalledWith('login');
  });

  it('offline: names the real problem — the request never reached the server', async () => {
    const spy = vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(false);
    renderCta({ onAction: async () => { throw new Error('fetch failed'); } });
    const btn = screen.getByRole('button');
    await act(async () => void fireEvent.click(btn));
    expect(btn).toHaveAttribute('data-state', 'offline');
    expect(visibleLabel(btn)).toBe('You are offline — retry');
    spy.mockRestore();
  });

  it('handled: another surface continues the flow — no success, no failure, silent idle', async () => {
    renderCta({ onAction: async () => 'handled' as const });
    const btn = screen.getByRole('button');
    await act(async () => void fireEvent.click(btn));
    expect(btn).toHaveAttribute('data-state', 'idle');
    expect(visibleLabel(btn)).toBe('Save look');
  });

  it('outcomeFromResult maps the viewmodel convention honestly', () => {
    expect(outcomeFromResult(true)).toBe('success');
    expect(outcomeFromResult(false)).toBe('error');
    expect(outcomeFromResult(undefined)).toBe('handled');
  });

  it('state is announced in a polite live region as TEXT (never animation-only)', async () => {
    const d = deferred<void>();
    renderCta({ onAction: () => d.promise });
    fireEvent.click(screen.getByRole('button'));
    const region = screen.getAllByRole('status').find((el) => el.getAttribute('aria-live') === 'polite')!;
    expect(region).toHaveTextContent('Saving…');
    await act(async () => { d.resolve(); await Promise.resolve(); });
    expect(region).toHaveTextContent('Look saved');
  });
});

/* ------------------------------------------------------------------ */
/* B. Trust guarantees                                                 */
/* ------------------------------------------------------------------ */
describe('ActionButton trust guarantees', () => {
  it('no double submit: double-click during flight sends exactly once (§9)', async () => {
    const d = deferred<void>();
    const action = vi.fn(() => d.promise);
    renderCta({ onAction: action });
    const btn = screen.getByRole('button');
    fireEvent.click(btn);
    fireEvent.click(btn);
    fireEvent.click(btn);
    await act(async () => { d.resolve(); await Promise.resolve(); });
    expect(action).toHaveBeenCalledTimes(1);
  });

  it('focus never drops: the control is NOT `disabled` while pending (§9)', async () => {
    const d = deferred<void>();
    renderCta({ onAction: () => d.promise });
    const btn = screen.getByRole('button');
    btn.focus();
    fireEvent.click(btn);
    // Real browsers eject focus from a disabled element — so pending must
    // be expressed with aria-disabled + click guard, never the attribute.
    expect(btn).not.toBeDisabled();
    expect(btn).toHaveAttribute('aria-disabled', 'true');
    expect(btn).toHaveFocus();
    await act(async () => { d.resolve(); await Promise.resolve(); });
    expect(btn).toHaveFocus();
  });

  it('layout reservation: every state label is pre-rendered in one grid cell + fixed min-height (§6.3)', () => {
    renderCta({ onAction: async () => {} });
    const btn = screen.getByRole('button');
    expect(btn.className).toContain('min-h-[44px]');
    const stack = screen.getByTestId('cta-label-stack');
    const texts = Array.from(stack.children).map((c) => c.textContent);
    for (const label of Object.values(LABELS)) expect(texts).toContain(label);
    // Exactly one label is visible; the rest reserve width invisibly.
    const visible = Array.from(stack.children).filter((c) => !c.className.includes('invisible'));
    expect(visible).toHaveLength(1);
  });

  it('cancellation is not failure: AbortError returns silently to idle (§5)', async () => {
    renderCta({
      onAction: async () => {
        const err = new DOMException('The user aborted a request.', 'AbortError');
        throw err;
      },
    });
    const btn = screen.getByRole('button');
    await act(async () => void fireEvent.click(btn));
    expect(btn).toHaveAttribute('data-state', 'idle');
    expect(visibleLabel(btn)).toBe('Save look');
  });

  it('slow API: pending persists exactly until the server answers — never times out into fake success (§10)', async () => {
    vi.useFakeTimers();
    const d = deferred<void>();
    renderCta({ onAction: () => d.promise });
    const btn = screen.getByRole('button');
    fireEvent.click(btn);
    // 30 simulated seconds of slow API: still honestly pending.
    act(() => void vi.advanceTimersByTime(30000));
    expect(btn).toHaveAttribute('data-state', 'pending');
    expect(btn).toHaveAttribute('aria-busy', 'true');
    await act(async () => { d.resolve(); await Promise.resolve(); });
    expect(btn).toHaveAttribute('data-state', 'success');
  });

  it('softDisabled (sibling in flight): clicks swallowed via aria-disabled, NEVER the disabled attribute — focus intact', () => {
    const action = vi.fn();
    renderCta({ onAction: action, softDisabled: true });
    const btn = screen.getByRole('button');
    // The lockout must not eject keyboard focus the way `disabled` would.
    expect(btn).not.toBeDisabled();
    expect(btn).toHaveAttribute('aria-disabled', 'true');
    btn.focus();
    expect(btn).toHaveFocus();
    fireEvent.click(btn);
    expect(action).not.toHaveBeenCalled();
    expect(btn).toHaveFocus();
  });

  it('publish contract (my-looks): server link → success, null verdict → actionable error', async () => {
    // Mirrors SharePanel's adoption: the viewmodel returns the minted link
    // or null (toast already carries the server reason).
    let serverResult: object | null = null;
    renderCta({
      onAction: async () => (serverResult ? ('success' as const) : ('error' as const)),
      metricsId: 'looks.publish_link',
    });
    const btn = screen.getByRole('button');
    await act(async () => void fireEvent.click(btn));
    expect(btn).toHaveAttribute('data-state', 'error'); // no link = no success claim
    serverResult = { share_url: '/looks/tok_x' };
    await act(async () => void fireEvent.click(btn));
    expect(btn).toHaveAttribute('data-state', 'success');
    expect(getCtaMetrics().map((m) => m.outcome)).toEqual(['error', 'success']);
  });

  it('caller-level disabled still works for real preconditions (empty cart, invalid look)', () => {
    const action = vi.fn();
    renderCta({ onAction: action, disabled: true });
    const btn = screen.getByRole('button');
    expect(btn).toBeDisabled();
    fireEvent.click(btn);
    expect(action).not.toHaveBeenCalled();
  });
});

/* ------------------------------------------------------------------ */
/* C. Controlled / financial mode (checkout + try-on contracts)        */
/* ------------------------------------------------------------------ */
describe('ActionButton controlled mode', () => {
  it('checkout contract: caller owns pending; the button NEVER paints success locally (§2/§9)', async () => {
    // The server reply is held open until the test has observed the pending
    // state. A fixed-length timer here raced the first waitFor poll (CI flake:
    // the reply landed before aria-busy was observed, so data-state read 'idle').
    const reply = deferred<void>();
    const Harness: React.FC = () => {
      const [submitting, setSubmitting] = React.useState(false);
      const [confirmed, setConfirmed] = React.useState(false);
      const placeOrder = async () => {
        setSubmitting(true);
        try {
          await reply.promise;
          setConfirmed(true); // ← the server reply is the ONLY success surface
        } finally {
          setSubmitting(false);
        }
      };
      return (
        <form onSubmit={(e) => { e.preventDefault(); void placeOrder(); }}>
          <ActionButton
            type="submit"
            financial
            state={submitting ? 'pending' : 'idle'}
            labels={{ idle: 'Place order', pending: 'Placing order…', error: 'Order not placed — retry' }}
          />
          {confirmed && <p>Order confirmed by server</p>}
        </form>
      );
    };
    render(<I18nextProvider i18n={i18n}><Harness /></I18nextProvider>);
    const btn = screen.getByRole('button');
    expect(btn).toHaveAttribute('data-financial', 'true');
    fireEvent.click(btn);
    await waitFor(() => expect(btn).toHaveAttribute('aria-busy', 'true'));
    // While the server has not replied there is NO success claim anywhere.
    expect(btn).toHaveAttribute('data-state', 'pending');
    expect(screen.queryByText('Order confirmed by server')).not.toBeInTheDocument();
    await act(async () => { reply.resolve(); await Promise.resolve(); });
    await waitFor(() => expect(screen.getByText('Order confirmed by server')).toBeInTheDocument());
    // The button itself returned to idle — success was the server surface.
    expect(btn).toHaveAttribute('data-state', 'idle');
  });

  it('checkout error: a rejected submit returns the CTA to an actionable state, no success claim', async () => {
    const onError = vi.fn();
    const Harness: React.FC = () => {
      const [submitting, setSubmitting] = React.useState(false);
      const [failed, setFailed] = React.useState(false);
      const placeOrder = async () => {
        setSubmitting(true);
        setFailed(false);
        try {
          await Promise.reject(new Error('card declined'));
        } catch (e) {
          onError(e); // checkout surfaces the localized server reason as a toast
          setFailed(true);
        } finally {
          setSubmitting(false);
        }
      };
      return (
        <ActionButton
          financial
          state={submitting ? 'pending' : failed ? 'error' : 'idle'}
          onPress={() => void placeOrder()}
          labels={{ idle: 'Place order', pending: 'Placing order…', error: 'Order not placed — retry' }}
        />
      );
    };
    render(<I18nextProvider i18n={i18n}><Harness /></I18nextProvider>);
    const btn = screen.getByRole('button');
    fireEvent.click(btn);
    await waitFor(() => expect(btn).toHaveAttribute('data-state', 'error'));
    expect(visibleLabel(btn)).toBe('Order not placed — retry');
    expect(onError).toHaveBeenCalled();
    // Still clickable — failure is actionable (§9).
    fireEvent.click(btn);
    await waitFor(() => expect(btn).toHaveAttribute('data-state', 'error'));
  });

  it('try-on contract: controlled pending swallows clicks (one render per activation)', () => {
    const run = vi.fn();
    render(
      <I18nextProvider i18n={i18n}>
        <ActionButton
          state="pending"
          onPress={run}
          labels={{ idle: 'Run try-on', pending: 'Rendering…', error: 'Render failed — retry' }}
        />
      </I18nextProvider>,
    );
    const btn = screen.getByRole('button');
    fireEvent.click(btn);
    fireEvent.click(btn);
    expect(run).not.toHaveBeenCalled();
    expect(visibleLabel(btn)).toBe('Rendering…');
  });
});

/* ------------------------------------------------------------------ */
/* D. Metrics (§6.5 — non-sensitive only)                              */
/* ------------------------------------------------------------------ */
describe('CTA metrics', () => {
  it('records static id + duration + outcome word — and nothing else', async () => {
    renderCta({ metricsId: 'builder.save_look', onAction: async () => {} });
    await act(async () => void fireEvent.click(screen.getByRole('button')));
    const metrics = getCtaMetrics();
    expect(metrics).toHaveLength(1);
    expect(metrics[0].id).toBe('builder.save_look');
    expect(metrics[0].outcome).toBe('success');
    expect(metrics[0].durationMs).toBeGreaterThanOrEqual(0);
    expect(Object.keys(metrics[0]).sort()).toEqual(['at', 'durationMs', 'id', 'outcome']);
  });

  it('records failures too (duration of the failed attempt, outcome word only)', async () => {
    renderCta({ metricsId: 'builder.save_look', onAction: async () => { throw new Error('boom with secret sku-123'); } });
    await act(async () => void fireEvent.click(screen.getByRole('button')));
    const [m] = getCtaMetrics();
    expect(m.outcome).toBe('error');
    expect(JSON.stringify(m)).not.toContain('sku-123'); // no payload leakage
  });

  it('no metricsId → nothing recorded', async () => {
    renderCta({ onAction: async () => {} });
    await act(async () => void fireEvent.click(screen.getByRole('button')));
    expect(getCtaMetrics()).toHaveLength(0);
  });
});

/* ------------------------------------------------------------------ */
/* E. axe · RTL · reduced motion                                       */
/* ------------------------------------------------------------------ */
describe('ActionButton a11y & motion', () => {
  it('axe: no violations in EN/LTR (all states reachable as text)', async () => {
    const { container } = renderCta({ onAction: async () => {} });
    const results = await axe(container, {
      rules: { 'color-contrast': { enabled: false }, 'target-size': { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });

  it('axe + Arabic labels in AR/RTL', async () => {
    await setAppLanguage('ar');
    const { container } = render(
      <I18nextProvider i18n={i18n}>
        <ActionButton
          labels={{
            idle: i18n.t('outfit_builder.save_outfit'),
            pending: i18n.t('outfit_builder.saving'),
            success: i18n.t('outfit_builder.saved_confirm'),
            error: i18n.t('outfit_builder.save_failed_retry'),
          }}
          onAction={async () => {}}
        />
      </I18nextProvider>,
    );
    expect(document.documentElement.dir).toBe('rtl');
    expect(screen.getByRole('button', { name: /حفظ/ })).toBeInTheDocument();
    const results = await axe(container, {
      rules: { 'color-contrast': { enabled: false }, 'target-size': { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });

  it('reduced motion: renders a PLAIN button (no kinetic wrapper) with full function (§7)', async () => {
    const original = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      matches: query.includes('prefers-reduced-motion'),
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
    try {
      const action = vi.fn(async () => {});
      renderCta({ onAction: action });
      const btn = screen.getByRole('button');
      await act(async () => void fireEvent.click(btn));
      expect(action).toHaveBeenCalledTimes(1);
      expect(btn).toHaveAttribute('data-state', 'success');
      // Spinner uses motion-safe: so even its spin is off under reduce.
      expect(visibleLabel(btn)).toBe('Look saved');
    } finally {
      window.matchMedia = original;
    }
  });

  it('keyboard: natively focusable button, activation guarded exactly like pointer input', async () => {
    const d = deferred<void>();
    const action = vi.fn(() => d.promise);
    renderCta({ onAction: action });
    const btn = screen.getByRole('button');
    btn.focus();
    expect(btn).toHaveFocus();
    // Native <button> maps Enter/Space to click; jsdom models that as click.
    fireEvent.click(btn);
    fireEvent.click(btn); // key-repeat during pending must not double-send
    await act(async () => { d.resolve(); await Promise.resolve(); });
    expect(action).toHaveBeenCalledTimes(1);
    expect(btn).toHaveFocus();
  });
});
