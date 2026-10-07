/**
 * Spec 02 re-pass — deep links and translated auth failures.
 *
 * What this file pins (gaps found in the re-audit, now fixed):
 *
 *   1. §9 "deep link works": `?auth=signin|signup|forgot` on any route opens
 *      the modal on that exact step, the param is stripped with a REPLACE
 *      (Back never re-opens the modal), and the shopper stays on the route
 *      the link pointed to. Garbage values are ignored — no modal.
 *   2. §6 "MFA/error messages translated": authStore used to surface the raw
 *      English server string ("Invalid email or password.") straight into the
 *      role="alert" region — an Arabic shopper read English on every failed
 *      login. Now the UI translates by ApiError.code:
 *        AUTH_FAILED  on signin → auth.invalid_credentials
 *        AUTH_FAILED  on MFA    → auth.mfa_code_invalid
 *        NETWORK_ERROR          → errors.network (shared map)
 *      in BOTH locales, asserted against the real catalogue strings.
 *   3. The dialog's heading is VISIBLE (not sr-only) and names the step.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import React from 'react';
import { render, screen, cleanup, fireEvent, act, waitFor } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter, useLocation } from 'react-router-dom';

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
    },
  };
});

import { authService } from '../../services/apiServices';
import { useAuthStore } from '../../stores/authStore';
import { useUIStore } from '../../stores/uiStore';
import { AuthModal } from '../auth/AuthModal';

const mockedLogin = authService.login as ReturnType<typeof vi.fn>;

function LocationProbe() {
  const location = useLocation();
  return (
    <>
      <span data-testid="probe-path">{location.pathname}</span>
      <span data-testid="probe-search">{location.search}</span>
    </>
  );
}

function renderModal(initialRoute = '/discover') {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={[initialRoute]}>
        <AuthModal />
        <LocationProbe />
      </MemoryRouter>
    </I18nextProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuthStore.setState({
    user: null,
    isAuthenticated: false,
    isLoading: false,
    error: null,
    errorCode: null,
    mfaRequired: false,
  } as any);
  useUIStore.setState({
    isAuthModalOpen: false,
    authModalMode: 'login',
    pendingAuthIntent: null,
    authReturnTo: null,
    toast: null,
  } as any);
});

afterEach(() => {
  cleanup();
  setAppLanguage('en');
});

describe('deep link opens the modal on the linked step (§9)', () => {
  it('?auth=signup opens Create account on the same route and strips the param', async () => {
    renderModal('/discover?auth=signup');

    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    // Signup step: the Full name field only exists on Create account.
    expect(await screen.findByLabelText('Full name')).toBeInTheDocument();
    // The shopper is still exactly where the link pointed…
    expect(screen.getByTestId('probe-path')).toHaveTextContent('/discover');
    // …and the trigger param is gone, so the URL is clean/shareable.
    await waitFor(() => expect(screen.getByTestId('probe-search')).toHaveTextContent(/^$/));
  });

  it('?auth=forgot lands directly on the reset step', async () => {
    renderModal('/product/silk-dress?auth=forgot');

    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'Send reset link' })).toBeInTheDocument();
    expect(screen.getByTestId('probe-path')).toHaveTextContent('/product/silk-dress');
    await waitFor(() => expect(screen.getByTestId('probe-search')).toHaveTextContent(/^$/));
  });

  it('other query params survive the strip', async () => {
    renderModal('/discover?q=linen&auth=signin&sort=new');

    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    await waitFor(() => {
      const search = screen.getByTestId('probe-search').textContent ?? '';
      expect(search).not.toContain('auth=');
      expect(search).toContain('q=linen');
      expect(search).toContain('sort=new');
    });
  });

  it('a garbage value opens nothing', async () => {
    renderModal('/discover?auth=lolwut');

    await waitFor(() => expect(screen.getByTestId('probe-search')).toHaveTextContent(/^$/));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});

describe('auth failures are translated by code, never raw server English (§6)', () => {
  const authFailed = () =>
    Object.assign(new Error('Invalid email or password.'), { status: 401, code: 'AUTH_FAILED' });

  async function failLogin() {
    fireEvent.change(screen.getByLabelText(/email|البريد/i), { target: { value: 's@x.io' } });
    fireEvent.change(screen.getByLabelText(/^password$|كلمة المرور/i, { selector: 'input' }), {
      target: { value: 'wrong-pass-1' },
    });
    fireEvent.click(screen.getByRole('button', { name: /sign in|تسجيل الدخول/i }));
    return screen.findByRole('alert');
  }

  it('EN: wrong credentials show the login-context copy, not the session-expiry copy', async () => {
    mockedLogin.mockRejectedValue(authFailed());
    act(() => useUIStore.getState().openAuthModal('login'));
    renderModal();

    const alert = await failLogin();
    expect(alert).toHaveTextContent('Incorrect email or password. Please try again.');
    // Neither the raw server string nor the generic AUTH_FAILED copy leaks in.
    expect(alert).not.toHaveTextContent('Invalid email or password.');
    expect(alert).not.toHaveTextContent('Your session has expired');
  });

  it('AR: the same failure reads in Arabic', async () => {
    await act(async () => {
      await setAppLanguage('ar');
    });
    mockedLogin.mockRejectedValue(authFailed());
    act(() => useUIStore.getState().openAuthModal('login'));
    renderModal();

    const alert = await failLogin();
    expect(alert).toHaveTextContent('البريد الإلكتروني أو كلمة المرور غير صحيحة. حاول مرة أخرى.');
    expect(alert).not.toHaveTextContent('Invalid email or password.');
  });

  it('a bad MFA code gets the MFA-context message, not the credentials one', async () => {
    // First submit: server demands MFA (a state, not an error).
    mockedLogin.mockRejectedValueOnce(
      Object.assign(new Error('MFA code required for this account.'), {
        status: 401,
        code: 'AUTH_FAILED',
        details: { reason: 'MFA_REQUIRED' },
      }),
    );
    act(() => useUIStore.getState().openAuthModal('login'));
    renderModal();

    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 's@x.io' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'Right-pass-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    const codeInput = await screen.findByLabelText('MFA code / recovery code');
    // Second submit: wrong code.
    mockedLogin.mockRejectedValueOnce(
      Object.assign(new Error('Invalid MFA verification code.'), {
        status: 401,
        code: 'AUTH_FAILED',
      }),
    );
    fireEvent.change(codeInput, { target: { value: '000000' } });
    fireEvent.click(screen.getByRole('button', { name: /verify/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'That verification code is not valid. Check your authenticator app and try again.',
    );
  });

  it('a network failure uses the shared transport copy', async () => {
    mockedLogin.mockRejectedValue(
      Object.assign(new Error('fetch failed'), { code: 'NETWORK_ERROR' }),
    );
    act(() => useUIStore.getState().openAuthModal('login'));
    renderModal();

    const alert = await failLogin();
    expect(alert).toHaveTextContent(
      'Network connection failed. Check your connection and try again.',
    );
  });
});

describe('the step heading is visible, not screen-reader-only (§9)', () => {
  it('signin shows its heading as real visible text naming the dialog', () => {
    act(() => useUIStore.getState().openAuthModal('login'));
    renderModal();

    const heading = screen.getByRole('heading', { name: 'Sign in to CONFIT' });
    expect(heading).toBeVisible();
    expect(heading.className).not.toContain('sr-only');
    // The same node is the dialog's accessible name.
    expect(screen.getByRole('dialog')).toHaveAttribute('aria-labelledby', heading.id);
  });

  it('switching to signup renames the visible heading', async () => {
    act(() => useUIStore.getState().openAuthModal('register'));
    renderModal();

    expect(await screen.findByRole('heading', { name: 'Create your CONFIT account' })).toBeVisible();
  });
});
