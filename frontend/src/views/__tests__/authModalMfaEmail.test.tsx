/**
 * MFA second factor by EMAIL (2026-10-06) — the chooser in the two-factor
 * step of the auth modal.
 *
 * Contract pinned here:
 *   · 'Authenticator app' stays the DEFAULT — the email path is opt-in and
 *     NOTHING is sent until the shopper presses the send button (no
 *     surprise emails on merely opening the step).
 *   · "Code sent" appears only after the server said "sent" (the transport
 *     really accepted the message); the masked destination and expiry come
 *     from the server's answer, never invented client-side.
 *   · A failed send is an honest failure state with no cooldown lock-out
 *     lie, and the resend cooldown only arms after a REAL send.
 *   · Verify & sign in submits whatever method's code through the same
 *     completeMfaLogin path.
 *   · EN/AR translated; the radiogroup is accessible; axe clean.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import React from 'react';
import { render, screen, cleanup, fireEvent, act, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { axe } from 'vitest-axe';

import i18n, { setAppLanguage } from '../../i18n/i18n';

vi.mock('../../services/apiServices', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../services/apiServices')>();
  return {
    ...original,
    authService: {
      ...original.authService,
      login: vi.fn(),
      register: vi.fn(),
      forgotPassword: vi.fn(),
      requestMfaEmailCode: vi.fn(),
    },
  };
});

import { authService } from '../../services/apiServices';
import { useAuthStore } from '../../stores/authStore';
import { useUIStore } from '../../stores/uiStore';
import { AuthModal } from '../auth/AuthModal';

const requestCode = vi.mocked(authService.requestMfaEmailCode);

const AXE_RULES = {
  rules: { 'color-contrast': { enabled: false }, 'target-size': { enabled: false } },
};

function renderModal() {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={['/discover']}>
        <AuthModal />
      </MemoryRouter>
    </I18nextProvider>,
  );
}

/** Open the modal in the MFA step the way the store actually gets there. */
function openAtMfaStep() {
  act(() => {
    useUIStore.getState().openAuthModal('login');
  });
  act(() => {
    useAuthStore.setState({ mfaRequired: true } as any);
  });
}

beforeEach(async () => {
  vi.clearAllMocks();
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false, media: query, onchange: null,
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
    addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
  }));
  await act(async () => { await setAppLanguage('en'); });
  useAuthStore.setState({
    user: null, isAuthenticated: false, isLoading: false,
    error: null, errorCode: null, mfaRequired: false,
  } as any);
  useUIStore.setState({
    isAuthModalOpen: false, authModalMode: 'login',
    pendingAuthIntent: null, authReturnTo: null, toast: null,
  } as any);
});

afterEach(async () => {
  cleanup();
  await act(async () => { await setAppLanguage('en'); });
});

describe('method chooser', () => {
  it('authenticator app is the default; NOTHING is sent on merely opening the step', async () => {
    renderModal();
    openAtMfaStep();
    const group = await screen.findByRole('radiogroup', {
      name: i18n.t('auth.mfa_method_label'),
    });
    const appRadio = screen.getByRole('radio', { name: i18n.t('auth.mfa_method_app') });
    expect(appRadio).toHaveAttribute('aria-checked', 'true');
    expect(group).toBeInTheDocument();
    expect(requestCode).not.toHaveBeenCalled();
    // app instructions visible, email send button not rendered yet
    expect(screen.getByText(i18n.t('auth.mfa_instructions'))).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: i18n.t('auth.mfa_email_send') }),
    ).not.toBeInTheDocument();
  });

  it('choosing email shows the send button — still nothing sent until pressed', async () => {
    renderModal();
    openAtMfaStep();
    fireEvent.click(await screen.findByRole('radio', { name: i18n.t('auth.mfa_method_email') }));
    expect(screen.getByText(i18n.t('auth.mfa_instructions_email'))).toBeInTheDocument();
    expect(screen.getByRole('button', { name: i18n.t('auth.mfa_email_send') })).toBeInTheDocument();
    expect(requestCode).not.toHaveBeenCalled();
  });
});

describe('sending the code', () => {
  it('"sent" appears ONLY after the server confirms; masked address + expiry are the server words', async () => {
    let resolveSend!: (v: any) => void;
    requestCode.mockReturnValue(new Promise((res) => { resolveSend = res; }));
    renderModal();
    openAtMfaStep();
    fireEvent.click(await screen.findByRole('radio', { name: i18n.t('auth.mfa_method_email') }));
    fireEvent.click(screen.getByRole('button', { name: i18n.t('auth.mfa_email_send') }));
    // in flight — no success claim yet
    expect(screen.getByRole('button', { name: i18n.t('auth.mfa_email_sending') })).toBeInTheDocument();
    expect(screen.queryByText(/Code sent to/)).not.toBeInTheDocument();
    await act(async () => {
      resolveSend({ status: 'sent', sent_to: 'om***@gmail.com', expires_in_minutes: 10 });
    });
    expect(
      screen.getByText(
        i18n.t('auth.mfa_email_sent_to', { email: 'om***@gmail.com', minutes: 10 }),
      ),
    ).toBeInTheDocument();
    // resend is now cooling down
    expect(
      screen.getByRole('button', { name: i18n.t('auth.mfa_email_resend_in', { seconds: 30 }) }),
    ).toBeDisabled();
  });

  it('a transport failure is an honest failure — no fake "check your inbox"', async () => {
    requestCode.mockRejectedValue({
      code: 'PROVIDER_ERROR',
      message: "Provider 'email' error: Could not deliver the MFA code",
      status: 502,
    });
    renderModal();
    openAtMfaStep();
    fireEvent.click(await screen.findByRole('radio', { name: i18n.t('auth.mfa_method_email') }));
    fireEvent.click(screen.getByRole('button', { name: i18n.t('auth.mfa_email_send') }));
    await waitFor(() =>
      expect(screen.getByText(i18n.t('auth.mfa_email_send_failed'))).toBeInTheDocument(),
    );
    expect(screen.queryByText(/Code sent/)).not.toBeInTheDocument();
    // the send button is immediately available again — no cooldown for a failure
    expect(screen.getByRole('button', { name: i18n.t('auth.mfa_email_send') })).not.toBeDisabled();
  });

  it('the emailed code goes through the same verify path', async () => {
    requestCode.mockResolvedValue({ status: 'sent', sent_to: 'om***@g.com', expires_in_minutes: 10 });
    const completeMfa = vi.fn().mockResolvedValue({ user: { role: 'consumer' } });
    useAuthStore.setState({ completeMfaLogin: completeMfa } as any);
    renderModal();
    openAtMfaStep();
    fireEvent.click(await screen.findByRole('radio', { name: i18n.t('auth.mfa_method_email') }));
    fireEvent.click(screen.getByRole('button', { name: i18n.t('auth.mfa_email_send') }));
    await screen.findByText(/Code sent to/);
    const input = screen.getByLabelText(i18n.t('auth.mfa_email_code_label'));
    expect(input).toHaveAttribute('dir', 'ltr'); // codes are tokens, LTR in AR too
    fireEvent.change(input, { target: { value: '042531' } });
    fireEvent.click(screen.getByRole('button', { name: i18n.t('auth.verify_sign_in') }));
    await waitFor(() => expect(completeMfa).toHaveBeenCalled());
    expect(completeMfa.mock.calls[0][2]).toBe('042531');
  });
});

describe('i18n + a11y', () => {
  it('AR: chooser and email flow fully translated; axe clean', async () => {
    await act(async () => { await setAppLanguage('ar'); });
    requestCode.mockResolvedValue({ status: 'sent', sent_to: 'om***@g.com', expires_in_minutes: 10 });
    renderModal();
    openAtMfaStep();
    fireEvent.click(await screen.findByRole('radio', { name: 'أرسلوا الرمز لبريدي' }));
    expect(screen.getByText(/يمكننا إرسال رمز مكوّن من 6 أرقام/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'إرسال الرمز إلى بريدي' }));
    await waitFor(() =>
      expect(screen.getByText(/تم إرسال الرمز إلى/)).toBeInTheDocument(),
    );
    const results = await axe(document.body, AXE_RULES);
    expect(results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical'))
      .toEqual([]);
  });
});
