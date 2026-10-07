/**
 * Auth cluster pass — contracts of the NEW shared layer.
 *
 *   A. PasswordPolicyChecklist mirrors the server policy (8–72, ≥3 classes)
 *      with state as TEXT (sr-only met/unmet), optional match row, axe.
 *   B. AuthPageShell: landmark + card, children rendered.
 *   C. AuthModal integration: password visibility toggle (type flips,
 *      aria-pressed, label from the shared reset_password keys) and the
 *      LIVE checklist on the signup step (static hint line is gone).
 */
import React from 'react';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, act } from '@testing-library/react';
import { axe } from 'vitest-axe';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';

import { vi } from 'vitest';

vi.mock('../../../services/apiServices', async (importOriginal) => {
  const original =
    await importOriginal<typeof import('../../../services/apiServices')>();
  return {
    ...original,
    authService: { ...original.authService, login: vi.fn() },
  };
});

import i18n from '../../../i18n/i18n';
import { authService } from '../../../services/apiServices';
import {
  PasswordPolicyChecklist,
  passwordPolicyMet,
} from '../PasswordPolicyChecklist';
import { AuthPageShell } from '../AuthPageShell';
import { useUIStore } from '../../../stores/uiStore';
import { AuthModal } from '../../../views/auth/AuthModal';

const wrap = (ui: React.ReactElement) =>
  render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>{ui}</MemoryRouter>
    </I18nextProvider>,
  );

afterEach(() => cleanup());

describe('A. PasswordPolicyChecklist', () => {
  it('mirrors the SERVER policy: helper and rows agree, rule by rule', () => {
    // Too short, one class only.
    expect(passwordPolicyMet('abc')).toBe(false);
    // 8+ chars but a single character class.
    expect(passwordPolicyMet('abcdefgh')).toBe(false);
    // 8–72 and three classes — the real server acceptance.
    expect(passwordPolicyMet('Abcdef1!')).toBe(true);
    // Over 72 chars fails even with all classes.
    expect(passwordPolicyMet('Aa1!' + 'x'.repeat(70))).toBe(false);

    wrap(<PasswordPolicyChecklist password="Abcdef1!" confirm="Abcdef1!" />);
    const met = i18n.t('reset_password.rule_met');
    // All three rows (length, categories, match) announce "met" as TEXT.
    expect(screen.getAllByText(new RegExp(met))).toHaveLength(3);
  });

  it('announces unmet rules as text, not colour alone', () => {
    wrap(<PasswordPolicyChecklist password="short" confirm="different" />);
    const unmet = i18n.t('reset_password.rule_unmet');
    expect(screen.getAllByText(new RegExp(unmet))).toHaveLength(3);
  });

  it('omits the match row when no confirm value is supplied (register form)', () => {
    wrap(<PasswordPolicyChecklist password="Abcdef1!" />);
    expect(
      screen.queryByText(new RegExp(i18n.t('reset_password.rule_match'))),
    ).toBeNull();
  });

  it('axe: no serious/critical violations', async () => {
    const { container } = wrap(
      <PasswordPolicyChecklist password="Abcdef1!" confirm="x" />,
    );
    const res = await axe(container, {
      rules: { 'color-contrast': { enabled: false } },
    });
    expect(
      res.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical'),
    ).toEqual([]);
  });
});

describe('B. AuthPageShell', () => {
  it('renders a main landmark with the children inside the card', () => {
    wrap(
      <AuthPageShell>
        <p>shell-child-content</p>
      </AuthPageShell>,
    );
    const main = screen.getByRole('main');
    expect(main).toBeInTheDocument();
    expect(screen.getByText('shell-child-content')).toBeInTheDocument();
  });
});

describe('C. AuthModal — cluster parity', () => {
  beforeEach(() => {
    act(() => {
      useUIStore.getState().openAuthModal('register');
    });
  });
  afterEach(() => {
    act(() => {
      useUIStore.getState().closeAuthModal();
    });
  });

  it('signup has the visibility toggle AND the live policy checklist (reset-page parity)', () => {
    wrap(<AuthModal />);
    const pw = document.getElementById('auth-password') as HTMLInputElement;
    expect(pw.type).toBe('password');

    const toggle = screen.getByRole('button', {
      name: i18n.t('reset_password.show_password'),
    });
    expect(toggle.getAttribute('aria-pressed')).toBe('false');
    fireEvent.click(toggle);
    expect(pw.type).toBe('text');
    expect(
      screen.getByRole('button', { name: i18n.t('reset_password.hide_password') })
        .getAttribute('aria-pressed'),
    ).toBe('true');

    // The LIVE checklist reacts to typing — unmet first, met after.
    fireEvent.change(pw, { target: { value: 'short' } });
    expect(
      screen.getAllByText(new RegExp(i18n.t('reset_password.rule_unmet'))).length,
    ).toBeGreaterThan(0);
    fireEvent.change(pw, { target: { value: 'Abcdef1!' } });
    expect(
      screen.getAllByText(new RegExp(i18n.t('reset_password.rule_met'))),
    ).toHaveLength(2); // length + categories; no match row in the modal
  });
});

describe('D. cluster pass 2 — caps lock, mobile hygiene, trims, 48px floor', () => {
  const mockedLogin = authService.login as ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockedLogin.mockReset();
    act(() => {
      useUIStore.getState().openAuthModal('login');
    });
  });
  afterEach(() => {
    act(() => {
      useUIStore.getState().closeAuthModal();
    });
  });

  it('warns while Caps Lock is on and clears the warning on blur', () => {
    wrap(<AuthModal />);
    const pw = document.getElementById('auth-password') as HTMLInputElement;
    const hint = i18n.t('auth.caps_lock_on');

    expect(screen.queryByText(hint)).toBeNull();
    fireEvent.keyDown(pw, { key: 'a', modifierCapsLock: true });
    expect(screen.getByText(hint)).toBeInTheDocument();
    // The OS state is read from the event — turning it off updates live.
    fireEvent.keyUp(pw, { key: 'CapsLock', modifierCapsLock: false });
    expect(screen.queryByText(hint)).toBeNull();
    // And a stale warning never survives leaving the field.
    fireEvent.keyDown(pw, { key: 'a', modifierCapsLock: true });
    fireEvent.blur(pw);
    expect(screen.queryByText(hint)).toBeNull();
  });

  it('email field refuses mobile keyboard "help" (no autocapitalize/autocorrect)', () => {
    wrap(<AuthModal />);
    const email = document.getElementById('auth-email') as HTMLInputElement;
    expect(email.getAttribute('autocapitalize')).toBe('none');
    expect(email.getAttribute('autocorrect')).toBe('off');
    expect(email.getAttribute('spellcheck')).toBe('false');
  });

  it('submits the TRIMMED email — invisible trailing spaces never cause AUTH_FAILED', async () => {
    mockedLogin.mockResolvedValue({
      access_token: 'at',
      refresh_token: 'rt',
      user: { id: 7, role: 'consumer', full_name: 'T', email: 's@x.io' },
    });
    wrap(<AuthModal />);
    fireEvent.change(document.getElementById('auth-email') as HTMLInputElement, {
      target: { value: '  shopper@confit.io  ' },
    });
    fireEvent.change(document.getElementById('auth-password') as HTMLInputElement, {
      target: { value: 'Password123!' },
    });
    fireEvent.click(screen.getByRole('button', { name: i18n.t('auth.sign_in') }));
    await screen.findByText(i18n.t('auth.sign_in'), {}, { timeout: 2000 }).catch(() => null);
    await vi.waitFor(() => expect(mockedLogin).toHaveBeenCalled());
    expect(mockedLogin).toHaveBeenCalledWith('shopper@confit.io', 'Password123!');
  });

  it('field and primary CTA stand on the 48px token floor', () => {
    wrap(<AuthModal />);
    const email = document.getElementById('auth-email') as HTMLInputElement;
    const submit = screen.getByRole('button', { name: i18n.t('auth.sign_in') });
    expect(email.className).toContain('min-h-12');
    expect(submit.className).toContain('min-h-12');
  });
});
