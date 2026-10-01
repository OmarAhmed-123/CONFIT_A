/**
 * Spec 02 — Auth / Sign-up transition contract tests.
 *
 * Adversarial, like the rest of the suite: each test pins a branch a happy
 * demo never shows.
 *
 *   1. Switching signin ⇄ signup ⇄ forgot keeps the shopper exactly where
 *      they were — the modal never navigates, so context survives.
 *   2. Register conflict (taken email) surfaces the server's message as
 *      text in an alert — no silent failure, no fake account.
 *   3. Forgot-password shows ONE fixed non-committal confirmation (the UI
 *      must not add an email-existence side channel on top of the server's
 *      non-committal contract), and surfaces the honest 501 when the
 *      deployment cannot send mail instead of pretending it queued one.
 *   4. The pending auth intent runs EXACTLY once after successful login.
 *   5. `returnTo` is honored once after login.
 *   6. An expired session reopens the auth modal — re-auth in place.
 *   7. Escape closes (focus contract lives in useModalFocus tests).
 *   8. The password typed into the form never reaches web storage.
 *   9. axe: no critical/serious violations, LTR and RTL.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import React from 'react';
import { render, screen, cleanup, fireEvent, waitFor, act } from '@testing-library/react';
import { axe } from 'vitest-axe';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter, useLocation } from 'react-router-dom';

import i18n, { setAppLanguage } from '../../i18n/i18n';

// Real stores, mocked network: the state machine under test is the real
// authStore/uiStore wiring, only authService is a test double.
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
import { SESSION_EXPIRED_EVENT } from '../../services/apiClient';
import { AuthModal } from '../auth/AuthModal';

const mockedLogin = authService.login as ReturnType<typeof vi.fn>;
const mockedRegister = authService.register as ReturnType<typeof vi.fn>;
const mockedForgot = authService.forgotPassword as ReturnType<typeof vi.fn>;

const LOGIN_OK = {
  access_token: 'at-test',
  refresh_token: 'rt-test',
  user: { id: 1, role: 'consumer', full_name: 'Test Shopper', email: 's@x.io' },
};

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="location-probe">{location.pathname}</span>;
}

function renderModal(initialRoute = '/product/silk-dress') {
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

describe('switching forms never costs the shopper their place', () => {
  it('signin → signup → forgot → signin all happen on the same route, same modal', async () => {
    act(() => useUIStore.getState().openAuthModal('login'));
    renderModal('/product/silk-dress');

    expect(screen.getByTestId('location-probe')).toHaveTextContent('/product/silk-dress');

    fireEvent.click(screen.getByRole('button', { name: 'Create an account' }));
    expect(await screen.findByLabelText('Full name')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Forgot your password?' }));
    expect(await screen.findByRole('button', { name: 'Send reset link' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Back to sign in' }));
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument();

    // No navigation happened at any point — context preserved by construction.
    expect(screen.getByTestId('location-probe')).toHaveTextContent('/product/silk-dress');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
});

describe('register conflict is a visible, textual failure', () => {
  it('a taken email shows the server message in an alert and creates no session', async () => {
    mockedRegister.mockRejectedValue(
      Object.assign(new Error('An account with this email already exists.'), {
        status: 409,
        code: 'EMAIL_TAKEN',
      }),
    );
    act(() => useUIStore.getState().openAuthModal('register'));
    renderModal();

    fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'Layla' } });
    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 'taken@x.io' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'Str0ng!Pass' } });
    fireEvent.click(screen.getByRole('button', { name: /create an account/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'An account with this email already exists.',
    );
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    // Modal stays open so the user can correct course — nothing was lost.
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
});

describe('forgot password adds no side channel and never fakes a sent mail', () => {
  it('shows one fixed non-committal confirmation on success', async () => {
    mockedForgot.mockResolvedValue({ status: 'success', message: 'server copy ignored' });
    act(() => useUIStore.getState().openAuthModal('login'));
    renderModal();

    fireEvent.click(screen.getByRole('button', { name: 'Forgot your password?' }));
    fireEvent.change(await screen.findByLabelText('Email address'), {
      target: { value: 'whoever@x.io' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Send reset link' }));

    // The UI's own fixed copy — identical whether or not the account exists.
    // (Appears twice by design: visible confirmation + aria-live region.)
    const confirmations = await screen.findAllByText(
      /If an account exists for this email, a reset link is on its way/,
    );
    expect(confirmations.length).toBeGreaterThanOrEqual(1);
  });

  it('surfaces the honest 501 when the deployment has no email provider', async () => {
    mockedForgot.mockRejectedValue(
      Object.assign(new Error('email_delivery not configured'), {
        status: 501,
        code: 'FEATURE_NOT_CONFIGURED',
      }),
    );
    act(() => useUIStore.getState().openAuthModal('login'));
    renderModal();

    fireEvent.click(screen.getByRole('button', { name: 'Forgot your password?' }));
    fireEvent.change(await screen.findByLabelText('Email address'), {
      target: { value: 'whoever@x.io' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Send reset link' }));

    const warnings = await screen.findAllByText(
      /not configured on this deployment yet, so no email was sent/,
    );
    expect(warnings.length).toBeGreaterThanOrEqual(1);
    // And it must NOT show the "check your inbox" copy — that mail does not exist.
    expect(screen.queryAllByText(/a reset link is on its way/)).toEqual([]);
  });
});

describe('pending intent and returnTo fire exactly once on success', () => {
  it('runs the intent once and clears it', async () => {
    mockedLogin.mockResolvedValue(LOGIN_OK);
    const intent = vi.fn();
    act(() => useUIStore.getState().openAuthModal('login', { intent }));
    renderModal();

    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 's@x.io' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'Str0ng!Pass' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => expect(intent).toHaveBeenCalledTimes(1));
    expect(useUIStore.getState().pendingAuthIntent).toBeNull();
    expect(useUIStore.getState().isAuthModalOpen).toBe(false);
  });

  it('closing the modal abandons the intent — it never fires later', async () => {
    const intent = vi.fn();
    act(() => useUIStore.getState().openAuthModal('login', { intent }));
    renderModal();

    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(useUIStore.getState().pendingAuthIntent).toBeNull();
    expect(intent).not.toHaveBeenCalled();
  });

  it('honors returnTo once after login', async () => {
    mockedLogin.mockResolvedValue(LOGIN_OK);
    act(() =>
      useUIStore.getState().openAuthModal('login', { returnTo: '/wardrobe' }),
    );
    renderModal('/product/silk-dress');

    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 's@x.io' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'Str0ng!Pass' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() =>
      expect(screen.getByTestId('location-probe')).toHaveTextContent('/wardrobe'),
    );
    expect(useUIStore.getState().authReturnTo).toBeNull();
  });
});

describe('expired session re-authenticates in place', () => {
  it('SESSION_EXPIRED_EVENT opens the auth modal without navigation', async () => {
    renderModal('/wardrobe');
    expect(useUIStore.getState().isAuthModalOpen).toBe(false);

    act(() => {
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    });

    await waitFor(() => expect(useUIStore.getState().isAuthModalOpen).toBe(true));
    // Still on /wardrobe — the shopper re-enters credentials where they stood.
    expect(screen.getByTestId('location-probe')).toHaveTextContent('/wardrobe');
  });
});

describe('keyboard and storage hygiene', () => {
  it('Escape closes the modal', async () => {
    act(() => useUIStore.getState().openAuthModal('login'));
    renderModal();
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(useUIStore.getState().isAuthModalOpen).toBe(false));
  });

  it('the typed password never reaches localStorage or sessionStorage', async () => {
    mockedLogin.mockResolvedValue(LOGIN_OK);
    const PASSWORD = 'Sup3r$ecretUnique!';
    const localSpy = vi.spyOn(Storage.prototype, 'setItem');

    act(() => useUIStore.getState().openAuthModal('login'));
    renderModal();

    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 's@x.io' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: PASSWORD } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => expect(useUIStore.getState().isAuthModalOpen).toBe(false));
    for (const call of localSpy.mock.calls) {
      expect(String(call[1])).not.toContain(PASSWORD);
    }
    localSpy.mockRestore();
  });
});

describe('accessibility in both directions', () => {
  async function expectNoSeriousViolations() {
    const dialog = screen.getByRole('dialog');
    const results = await axe(dialog);
    const serious = results.violations.filter((v) =>
      ['critical', 'serious'].includes(v.impact ?? ''),
    );
    expect(serious).toEqual([]);
  }

  it('axe: signin form, English/LTR', async () => {
    act(() => useUIStore.getState().openAuthModal('login'));
    renderModal();
    await expectNoSeriousViolations();
  });

  it('axe: signup form, Arabic/RTL', async () => {
    await act(async () => {
      await setAppLanguage('ar');
    });
    act(() => useUIStore.getState().openAuthModal('register'));
    renderModal();
    await expectNoSeriousViolations();
  });
});
