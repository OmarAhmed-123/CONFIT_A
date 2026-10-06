/**
 * Audit 2026-10-06 — the pages the product talked about but never built:
 *
 *  /reset-password   — the URL the reset EMAIL has carried since cycle 4;
 *                      the route never existed, so the loop was broken.
 *  /verify-email     — same break; no route, no service method.
 *  404               — the catch-all silently redirected home.
 *  Email preferences — the unsubscribe page promised "manage from account
 *                      settings" and nothing existed there.
 *
 * Contracts under test: policy checklist mirrors the SERVER rule; success
 * only after server confirmation; token redemption needs the explicit CTA
 * (scanner-safe); non-committal resend; honest 404 with real links;
 * switches render the server's answer, never an optimistic flip.
 * Plus: EN/AR + RTL, reduced-motion, axe.
 */
import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { axe } from 'vitest-axe';

import { ResetPasswordView } from '../public/ResetPasswordView';
import { VerifyEmailView } from '../public/VerifyEmailView';
import { NotFoundView } from '../public/NotFoundView';
import { EmailPreferencesSection } from '../../components/account/EmailPreferencesSection';
import { authService, emailService } from '../../services/apiServices';
import { setAppLanguage } from '../../i18n/i18n';
import i18n from '../../i18n/i18n';

const AXE_RULES = {
  rules: { 'color-contrast': { enabled: false }, 'target-size': { enabled: false } },
};

vi.mock('../../services/apiServices', async (importOriginal) => {
  const mod = await importOriginal<typeof import('../../services/apiServices')>();
  return {
    ...mod,
    authService: {
      ...mod.authService,
      resetPassword: vi.fn(),
      verifyEmail: vi.fn(),
      requestEmailVerification: vi.fn(),
    },
    emailService: {
      ...mod.emailService,
      getPreferences: vi.fn(),
      updatePreferences: vi.fn(),
    },
  };
});

const resetPassword = vi.mocked(authService.resetPassword);
const verifyEmail = vi.mocked(authService.verifyEmail);
const requestVerification = vi.mocked(authService.requestEmailVerification);
const getPreferences = vi.mocked(emailService.getPreferences);
const updatePreferences = vi.mocked(emailService.updatePreferences);

const renderAt = (url: string, path: string, el: React.ReactElement) =>
  render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path={path} element={el} />
      </Routes>
    </MemoryRouter>,
  );

beforeEach(async () => {
  cleanup();
  vi.clearAllMocks();
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false, media: query, onchange: null,
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
    addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
  }));
  await act(async () => { await setAppLanguage('en'); });
});

afterEach(() => cleanup());

/* ────────────────────────── /reset-password ────────────────────────── */

describe('ResetPasswordView', () => {
  const type = (id: string, value: string) =>
    fireEvent.change(document.getElementById(id)!, { target: { value } });

  it('submit stays disabled until the SERVER policy is mirrored green', async () => {
    renderAt('/reset-password?token=tok1', '/reset-password', <ResetPasswordView />);
    const btn = screen.getByRole('button', { name: new RegExp(i18n.t('reset_password.submit_cta')) });
    expect(btn).toBeDisabled();
    type('rp-new', 'short');
    expect(btn).toBeDisabled();
    type('rp-new', 'Str0ng!Pass');
    type('rp-confirm', 'Str0ng!Pass');
    await waitFor(() => expect(btn).not.toBeDisabled());
    // mismatch flips it back off
    type('rp-confirm', 'Str0ng!Pas');
    await waitFor(() => expect(btn).toBeDisabled());
    expect(resetPassword).not.toHaveBeenCalled();
  });

  it('success ONLY after server confirms; CTA routes to sign-in deep link', async () => {
    let resolve!: (v: any) => void;
    resetPassword.mockReturnValue(new Promise((res) => { resolve = res; }));
    renderAt('/reset-password?token=tok2', '/reset-password', <ResetPasswordView />);
    type('rp-new', 'Str0ng!Pass');
    type('rp-confirm', 'Str0ng!Pass');
    fireEvent.click(screen.getByRole('button', { name: new RegExp(i18n.t('reset_password.submit_cta')) }));
    expect(screen.queryByText(i18n.t('reset_password.done_title'))).not.toBeInTheDocument();
    await act(async () => { resolve({ status: 'success', message: 'ok' }); });
    expect(screen.getByText(i18n.t('reset_password.done_title'))).toBeInTheDocument();
    expect(screen.getByRole('link', { name: i18n.t('reset_password.signin_cta') }))
      .toHaveAttribute('href', '/?auth=signin');
    expect(resetPassword).toHaveBeenCalledWith('tok2', 'Str0ng!Pass');
  });

  it('expired/used token → server verdict shown + working path to a fresh link', async () => {
    resetPassword.mockRejectedValue({ code: 'AUTH_FAILED', message: 'Reset token has expired.' });
    renderAt('/reset-password?token=tokOld', '/reset-password', <ResetPasswordView />);
    type('rp-new', 'Str0ng!Pass');
    type('rp-confirm', 'Str0ng!Pass');
    fireEvent.click(screen.getByRole('button', { name: new RegExp(i18n.t('reset_password.submit_cta')) }));
    await waitFor(() =>
      expect(screen.getByRole('link', { name: i18n.t('reset_password.request_new_link') }))
        .toHaveAttribute('href', '/?auth=forgot'),
    );
    expect(screen.queryByText(i18n.t('reset_password.done_title'))).not.toBeInTheDocument();
  });

  it('missing token → honest dead end, no form', async () => {
    renderAt('/reset-password', '/reset-password', <ResetPasswordView />);
    expect(screen.getByText(i18n.t('reset_password.no_token_title'))).toBeInTheDocument();
    expect(document.getElementById('rp-new')).toBeNull();
    const results = await axe(document.body, AXE_RULES);
    expect(results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical'))
      .toEqual([]);
  });

  it('AR/RTL renders the full translated form; axe clean', async () => {
    await act(async () => { await setAppLanguage('ar'); });
    renderAt('/reset-password?token=tokAr', '/reset-password', <ResetPasswordView />);
    expect(screen.getByText('اختر كلمة مرور جديدة')).toBeInTheDocument();
    expect(screen.getByText(/من 8 إلى 72 حرفًا/)).toBeInTheDocument();
    const results = await axe(document.body, AXE_RULES);
    expect(results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical'))
      .toEqual([]);
    await act(async () => { await setAppLanguage('en'); });
  });
});

/* ────────────────────────── /verify-email ────────────────────────── */

describe('VerifyEmailView', () => {
  it('NEVER redeems on load — the explicit CTA fires the POST', async () => {
    verifyEmail.mockResolvedValue({ status: 'success', message: 'ok' });
    renderAt('/verify-email?token=vtok1', '/verify-email', <VerifyEmailView />);
    expect(verifyEmail).not.toHaveBeenCalled(); // scanner-safe
    fireEvent.click(screen.getByRole('button', { name: i18n.t('verify_email.confirm_cta') }));
    await waitFor(() =>
      expect(screen.getByText(i18n.t('verify_email.done_title'))).toBeInTheDocument(),
    );
    expect(verifyEmail).toHaveBeenCalledWith('vtok1');
    expect(screen.getByRole('link', { name: i18n.t('verify_email.continue_cta') }))
      .toHaveAttribute('href', '/discover');
  });

  it('expired link → server verdict + non-committal resend form', async () => {
    verifyEmail.mockRejectedValue({ code: 'AUTH_FAILED', message: 'Verification link has expired. Request a new one.' });
    requestVerification.mockResolvedValue({ status: 'queued', message: 'queued' });
    renderAt('/verify-email?token=vtokOld', '/verify-email', <VerifyEmailView />);
    fireEvent.click(screen.getByRole('button', { name: i18n.t('verify_email.confirm_cta') }));
    await waitFor(() =>
      expect(screen.getByText(/expired/i)).toBeInTheDocument(),
    );
    fireEvent.change(document.getElementById('ve-email')!, {
      target: { value: 'omar@example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: i18n.t('verify_email.resend_cta') }));
    await waitFor(() =>
      expect(screen.getByText(i18n.t('verify_email.resend_sent'))).toBeInTheDocument(),
    );
    expect(requestVerification).toHaveBeenCalledWith('omar@example.com');
  });

  it('missing token → straight to the recovery form; axe clean', async () => {
    renderAt('/verify-email', '/verify-email', <VerifyEmailView />);
    expect(screen.getByText(i18n.t('verify_email.error_title'))).toBeInTheDocument();
    expect(document.getElementById('ve-email')).not.toBeNull();
    const results = await axe(document.body, AXE_RULES);
    expect(results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical'))
      .toEqual([]);
  });

  it('AR: translated verdicts', async () => {
    await act(async () => { await setAppLanguage('ar'); });
    renderAt('/verify-email?token=vtokAr', '/verify-email', <VerifyEmailView />);
    expect(screen.getByText('أكّد بريدك الإلكتروني')).toBeInTheDocument();
    await act(async () => { await setAppLanguage('en'); });
  });
});

/* ────────────────────────────── 404 ────────────────────────────── */

describe('NotFoundView', () => {
  it('names the dead end, shows the failed path LTR, links are real and public-only', async () => {
    renderAt('/this/does-not-exist', '*', <NotFoundView />);
    expect(screen.getByText(i18n.t('not_found.title'))).toBeInTheDocument();
    const code = screen.getByText('/this/does-not-exist');
    expect(code.closest('[dir="ltr"]')).not.toBeNull();
    expect(screen.getByRole('link', { name: new RegExp(i18n.t('not_found.home_cta')) }))
      .toHaveAttribute('href', '/');
    expect(screen.getByRole('link', { name: new RegExp(i18n.t('not_found.discover_cta')) }))
      .toHaveAttribute('href', '/discover');
    // No permission-gated surface is ever linked here (spec 13 rule).
    expect(screen.queryByRole('link', { name: /admin|b2b/i })).not.toBeInTheDocument();
    const results = await axe(document.body, AXE_RULES);
    expect(results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical'))
      .toEqual([]);
  });

  it('reduced motion: page fully functional without the float animation', async () => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes('prefers-reduced-motion'), media: query, onchange: null,
      addEventListener: vi.fn(), removeEventListener: vi.fn(),
      addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
    }));
    renderAt('/nope', '*', <NotFoundView />);
    expect(screen.getByText(i18n.t('not_found.title'))).toBeInTheDocument();
    expect(screen.getByRole('button', { name: i18n.t('not_found.back_cta') })).toBeInTheDocument();
  });
});

/* ───────────────────── Email preferences in Settings ───────────────────── */

describe('EmailPreferencesSection', () => {
  const PREFS = {
    engagement: true,
    marketing: true,
    links: { engagement: 'https://x/e', marketing: 'https://x/m' },
    categories: {},
  };

  it('renders the server answer; toggle shows the SERVER result, not an optimistic flip', async () => {
    getPreferences.mockResolvedValue({ ...PREFS });
    let resolve!: (v: any) => void;
    updatePreferences.mockReturnValue(new Promise((res) => { resolve = res; }));
    render(<EmailPreferencesSection />);
    const sw = await screen.findByRole('switch', { name: i18n.t('email_prefs.marketing_title') });
    expect(sw).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(sw);
    // in flight: busy, NOT flipped
    expect(sw).toHaveAttribute('aria-busy', 'true');
    expect(sw).toHaveAttribute('aria-checked', 'true');
    await act(async () => { resolve({ ...PREFS, marketing: false }); });
    expect(sw).toHaveAttribute('aria-checked', 'false');
    expect(updatePreferences).toHaveBeenCalledWith({ marketing: false });
  });

  it('PUT failure → switch stays as the server last said; error spoken', async () => {
    getPreferences.mockResolvedValue({ ...PREFS });
    updatePreferences.mockRejectedValue({ code: 'HTTP_ERROR', message: '' });
    render(<EmailPreferencesSection />);
    const sw = await screen.findByRole('switch', { name: i18n.t('email_prefs.engagement_title') });
    fireEvent.click(sw);
    await waitFor(() => expect(sw).toHaveAttribute('aria-busy', 'false'));
    expect(sw).toHaveAttribute('aria-checked', 'true'); // unchanged — honest
    expect(screen.getByText(i18n.t('errors.request_failed'))).toBeInTheDocument();
  });

  it('transactional row has NO switch and says why; load failure offers retry; axe clean', async () => {
    getPreferences.mockRejectedValueOnce(new Error('down')).mockResolvedValueOnce({ ...PREFS });
    render(<EmailPreferencesSection />);
    const retry = await screen.findByRole('button', { name: i18n.t('email_prefs.retry') });
    fireEvent.click(retry);
    await screen.findByRole('switch', { name: i18n.t('email_prefs.engagement_title') });
    expect(screen.getAllByRole('switch')).toHaveLength(2); // transactional is not a switch
    expect(screen.getByText(i18n.t('email_prefs.transactional_always'))).toBeInTheDocument();
    const results = await axe(document.body, AXE_RULES);
    expect(results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical'))
      .toEqual([]);
  });
});
