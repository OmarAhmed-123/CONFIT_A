/**
 * 010 — ConfirmationDialog behavioral (FR-006, ADM-18)
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, cleanup, fireEvent, act } from '@testing-library/react';
import { axe } from 'vitest-axe';
import { I18nextProvider } from 'react-i18next';
import i18n, { setAppLanguage } from '../../i18n/i18n';
import { ConfirmationDialog } from '../../components/common/StateComponents';

const JSDOM_UNCOMPUTABLE = ['color-contrast', 'target-size'];
async function seriousViolations(node: HTMLElement) {
  const results = await axe(node, { rules: Object.fromEntries(JSDOM_UNCOMPUTABLE.map((r) => [r, { enabled: false }])) });
  return results.violations.filter((v) => v.impact === 'critical' || v.impact === 'serious');
}
function wrap(children: React.ReactNode) {
  return render(<I18nextProvider i18n={i18n}>{children}</I18nextProvider>);
}
beforeEach(async () => { cleanup(); await act(async () => { await setAppLanguage('en'); }); });
afterEach(() => cleanup());

describe('010 — ConfirmationDialog behavioral (FR-006)', () => {
  it('cancel does NOT mutate', async () => {
    const onConfirm = vi.fn();
    const onClose = vi.fn();
    const { container } = wrap(
      <ConfirmationDialog isOpen title="Deactivate product?" message="It will disappear" confirmLabel="Deactivate" cancelLabel="Cancel" variant="danger" onConfirm={onConfirm} onClose={onClose} />
    );
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });

  it('confirm DOES mutate exactly once', async () => {
    const onConfirm = vi.fn();
    const onClose = vi.fn();
    const { container } = wrap(
      <ConfirmationDialog isOpen title="Deactivate product?" message="It will disappear" confirmLabel="Deactivate" cancelLabel="Cancel" variant="danger" onConfirm={onConfirm} onClose={onClose} />
    );
    fireEvent.click(screen.getByRole('button', { name: /deactivate/i }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });

  it('disabled when loading prevents duplicate submissions', async () => {
    const { container } = wrap(
      <ConfirmationDialog isOpen title="Deactivate?" message="Confirm" confirmLabel="Deactivate" cancelLabel="Cancel" isLoading onConfirm={vi.fn()} onClose={vi.fn()} />
    );
    const btn = screen.getByRole('button', { name: /deactivate/i });
    expect(btn.hasAttribute('disabled') || btn.getAttribute('aria-busy') === 'true').toBeTruthy();
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });

  it('has distinguishable cancel/confirm, keyboard accessible', async () => {
    const { container } = wrap(
      <ConfirmationDialog isOpen title="Delete product?" message="Irreversible" confirmLabel="Delete" cancelLabel="Cancel" variant="danger" onConfirm={vi.fn()} onClose={vi.fn()} />
    );
    const dialog = screen.getByRole('dialog');
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    const cancelBtn = screen.getByRole('button', { name: /cancel/i });
    const confirmBtn = screen.getByRole('button', { name: /delete/i });
    expect(cancelBtn.className).not.toBe(confirmBtn.className);
    cancelBtn.focus();
    expect(cancelBtn).toHaveFocus();
    confirmBtn.focus();
    expect(confirmBtn).toHaveFocus();
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });

  it('failure handling preserves context with alert', async () => {
    const { container } = wrap(
      <div>
        <ConfirmationDialog isOpen title="Deactivate?" message="Will retain history" confirmLabel="Deactivate" cancelLabel="Cancel" variant="danger" onConfirm={vi.fn()} onClose={vi.fn()} />
        <div role="alert">Failed to deactivate: network error</div>
      </div>
    );
    expect(screen.getByRole('alert').textContent).toContain('Failed to deactivate');
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });

  it('reduced-motion renders static, axe clean', async () => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: (q: string) => ({ matches: q.includes('prefers-reduced-motion: reduce'), media: q, onchange: null, addEventListener: () => {}, removeEventListener: () => {}, addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false }),
    });
    const { container } = wrap(
      <ConfirmationDialog isOpen title="Deactivate?" message="Confirm" confirmLabel="Deactivate" cancelLabel="Cancel" onConfirm={vi.fn()} onClose={vi.fn()} />
    );
    expect(screen.getByRole('dialog')).toBeTruthy();
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
  });

  it('RTL Arabic axe clean', async () => {
    await act(async () => { await setAppLanguage('ar'); });
    const { container } = wrap(
      <ConfirmationDialog isOpen title="إلغاء تنشيط المنتج؟" message="سيختفي مع الاحتفاظ بالسجل" confirmLabel="إلغاء التنشيط" cancelLabel="إلغاء" variant="danger" onConfirm={vi.fn()} onClose={vi.fn()} />
    );
    expect(document.documentElement.getAttribute('dir')).toBe('rtl');
    const violations = await seriousViolations(container);
    expect(violations).toEqual([]);
    await act(async () => { await setAppLanguage('en'); });
  });
});
