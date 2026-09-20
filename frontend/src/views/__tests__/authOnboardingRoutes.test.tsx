/**
 * Auth / onboarding routing contract (2026-09-19).
 *
 * Incident under test: a signed-in consumer clicking "Partner Portal" landed on
 * a dead-end ROLE RESTRICTION screen (screenshot in the report) because the
 * link pointed straight at the brand-guarded area. These tests pin the fix:
 *
 *  1. every email link CONFIT sends has a real route (they used to fall through
 *     the catch-all to "/", so verification/reset silently did nothing);
 *  2. the consumer entry point leads to the partner workflow, not to a 403;
 *  3. the 403 itself is actionable and state-accurate (pending vs rejected vs
 *     verify-first vs suspended), and never grants access client-side;
 *  4. registration sends portal INTENT only — no role field exists on the wire;
 *  5. the verification screen never claims an email was sent when the server
 *     could not deliver it.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { act } from 'react';

const {
  verifyEmailMock,
  requestVerificationMock,
  emailStatusMock,
  previewInviteMock,
  submitApplicationMock,
  listApplicationsMock,
} = vi.hoisted(() => ({
  verifyEmailMock: vi.fn(),
  requestVerificationMock: vi.fn(),
  emailStatusMock: vi.fn(),
  previewInviteMock: vi.fn(),
  submitApplicationMock: vi.fn(),
  listApplicationsMock: vi.fn(),
}));

vi.mock('../../services/apiClient', () => ({
  setAuthTokens: vi.fn(),
  getAuthToken: () => null,
  getSessionToken: () => 'sess_test_token',
  clearAuthTokens: vi.fn(),
  SESSION_EXPIRED_EVENT: 'confit:session-expired',
  ApiError: class ApiError extends Error {
    code: string;
    status: number;
    constructor(message: string, code = 'API_ERROR', status = 500) {
      super(message);
      this.code = code;
      this.status = status;
    }
  },
  request: vi.fn(),
}));

vi.mock('../../services/apiServices', () => ({
  authService: {
    verifyEmail: (...a: unknown[]) => verifyEmailMock(...a),
    requestEmailVerification: (...a: unknown[]) => requestVerificationMock(...a),
    getEmailStatus: (...a: unknown[]) => emailStatusMock(...a),
    getMe: vi.fn(),
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
  },
  partnerService: {
    submitApplication: (...a: unknown[]) => submitApplicationMock(...a),
    listMine: (...a: unknown[]) => listApplicationsMock(...a),
    withdraw: vi.fn(),
  },
  invitationService: {
    preview: (...a: unknown[]) => previewInviteMock(...a),
    accept: vi.fn(),
  },
  brandTeamService: { listInvitations: vi.fn().mockResolvedValue([]), createInvitation: vi.fn(), revokeInvitation: vi.fn() },
  adminPartnerService: { list: vi.fn().mockResolvedValue({ items: [], count: 0 }), approve: vi.fn(), reject: vi.fn() },
}));

import { AppRoutes } from '../../router/AppRoutes';
import { RoleGuard } from '../../components/auth/RoleGuard';
import { useAuthStore } from '../../stores/authStore';
import { useUIStore } from '../../stores/uiStore';
import { AuthModal } from '../auth/AuthModal';
import '../../i18n/i18n';

const baseUser = {
  id: 7,
  email: 'ismaeil1234@gmail.com',
  full_name: 'Ismaeil',
  role: 'consumer',
  is_active: true,
  is_verified: true,
  has_profile: true,
  preferred_language: 'en',
  mfa_enabled: false,
  created_at: '2026-09-19T00:00:00Z',
};

function signIn(user: any) {
  act(() => {
    useAuthStore.setState({ user, isAuthenticated: true, hasAttemptedBootstrap: true });
  });
}

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>
  );

describe('auth lifecycle routes exist (email links land somewhere real)', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null, isAuthenticated: false, hasAttemptedBootstrap: true });
    listApplicationsMock.mockResolvedValue([]);
  });

  it('renders the verification screen for /verify-email while signed out', () => {
    renderAt('/verify-email');
    expect(screen.getByRole('heading', { name: /confirm your email address/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /send verification link/i })).toBeTruthy();
  });

  it('renders the reset-password screen with a token and refuses to fake success without one', () => {
    renderAt('/reset-password?token=abc123');
    expect(screen.getByText(/choose a new password/i)).toBeTruthy();

    renderAt('/reset-password');
    expect(screen.getByText(/reset link required/i)).toBeTruthy();
  });

  it('renders the partner application route for a consumer (the screenshot dead end is gone)', () => {
    signIn(baseUser);
    renderAt('/partner/apply');
    expect(screen.getByText(/apply for partner access/i)).toBeTruthy();
    // The CTA must reach the application form, not a 403 gate.
    expect(screen.queryByText(/access restricted/i)).toBeNull();
  });
});

describe('RoleGuard 403 is state-accurate and actionable', () => {
  it('sends a consumer without partner access to the application workflow', () => {
    signIn({ ...baseUser, partner_access: 'none' });
    render(
      <MemoryRouter initialEntries={['/b2b']}>
        <RoleGuard allowedRoles={['brand_owner', 'brand_manager', 'brand_staff', 'admin']}>
          <div>brand area</div>
        </RoleGuard>
      </MemoryRouter>
    );
    expect(screen.queryByText('brand area')).toBeNull();
    expect(screen.getByText(/apply for partner access/i)).toBeTruthy();
    expect(screen.getByText(/role restriction/i)).toBeTruthy();
  });

  it('shows review-in-progress with a status link when an application is pending', () => {
    signIn({ ...baseUser, partner_access: 'pending', partner_application_status: 'pending' });
    render(
      <MemoryRouter>
        <RoleGuard allowedRoles={['brand_owner', 'brand_manager', 'brand_staff']}>
          <div>brand area</div>
        </RoleGuard>
      </MemoryRouter>
    );
    expect(screen.getByText(/partner review in progress/i)).toBeTruthy();
    expect(screen.getByText(/view application status/i)).toBeTruthy();
  });

  it('asks for verification before partner access when the address is unverified', () => {
    signIn({
      ...baseUser,
      is_verified: false,
      partner_access: 'none',
      onboarding: { account_state: 'EMAIL_VERIFICATION_REQUIRED', registration_intent: 'consumer' },
    });
    render(
      <MemoryRouter>
        <RoleGuard allowedRoles={['brand_owner', 'brand_manager', 'brand_staff']}>
          <div>brand area</div>
        </RoleGuard>
      </MemoryRouter>
    );
    expect(screen.getByText(/verify your email first/i)).toBeTruthy();
  });

  it('never grants access client-side for a forged privileged state', () => {
    signIn({ ...baseUser, role: 'consumer', allowed_areas: ['storefront', 'b2b'] });
    render(
      <MemoryRouter>
        <RoleGuard allowedRoles={['brand_owner']}>
          <div>brand area</div>
        </RoleGuard>
      </MemoryRouter>
    );
    expect(screen.queryByText('brand area')).toBeNull();
  });

  it('renders the guarded area for the role the SERVER returned', () => {
    signIn({ ...baseUser, role: 'brand_owner', partner_access: 'approved' });
    render(
      <MemoryRouter>
        <RoleGuard allowedRoles={['brand_owner', 'brand_manager', 'brand_staff']}>
          <div>brand area</div>
        </RoleGuard>
      </MemoryRouter>
    );
    expect(screen.getByText('brand area')).toBeTruthy();
  });
});

describe('registration carries intent, never a role', () => {
  it('posts registration_intent and no role field', async () => {
    const registerMock = vi.fn().mockResolvedValue({
      user: { ...baseUser, registration_intent: 'brand_partner', onboarding: { next_action: { type: 'verify_email', route: '/verify-email' } } },
    });
    useAuthStore.setState({ register: registerMock as any, isLoading: false, error: null });
    useUIStore.setState({ isAuthModalOpen: true, authModalMode: 'register' });

    render(
      <MemoryRouter>
        <AuthModal />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByText(/join as brand/i));
    fireEvent.change(screen.getByPlaceholderText(/layla/i), { target: { value: 'Ismaeil' } });
    fireEvent.change(screen.getByPlaceholderText(/name@example.com/i), { target: { value: 'ismaeil1234@gmail.com' } });
    fireEvent.change(screen.getByPlaceholderText(/8\+ chars/i), { target: { value: 'Str0ng!Passw0rd' } });
    fireEvent.click(screen.getByRole('button', { name: /create account/i }));

    await waitFor(() => expect(registerMock).toHaveBeenCalledTimes(1));
    const payload = registerMock.mock.calls[0][0];
    expect(payload.registration_intent).toBe('brand_partner');
    expect(payload).not.toHaveProperty('role');
  });
});

describe('email screens never claim more than the server confirmed', () => {
  it('says plainly that nothing was sent when no provider is configured (501)', async () => {
    const { ApiError } = await import('../../services/apiClient');
    requestVerificationMock.mockRejectedValue(
      new ApiError('Email delivery is not configured.', 'FEATURE_NOT_CONFIGURED', 501)
    );
    emailStatusMock.mockResolvedValue({ status: 'blocked', accepted: false, attempts: 0, error_class: 'provider_not_configured' });
    signIn({ ...baseUser, is_verified: false });

    renderAt('/verify-email');
    fireEvent.change(screen.getByPlaceholderText(/you@example.com/i), { target: { value: 'ismaeil1234@gmail.com' } });
    fireEvent.click(screen.getByRole('button', { name: /send verification link/i }));

    await waitFor(() =>
      expect(screen.getByText(/Email delivery is not configured in this environment/i)).toBeTruthy()
    );
    expect(screen.getByText(/nothing was sent/i)).toBeTruthy();
  });

  it('reports the ledger truth for the account owner (accepted vs not accepted)', async () => {
    requestVerificationMock.mockResolvedValue({ status: 'requested', message: 'ok' });
    emailStatusMock.mockResolvedValue({ status: 'failed', accepted: false, attempts: 2, error_class: 'EmailDeliveryError' });
    signIn({ ...baseUser, is_verified: false });

    renderAt('/verify-email');
    await waitFor(() => expect(screen.getByText(/no message was accepted by the mail server/i)).toBeTruthy());
    expect(screen.getByText(/failed/)).toBeTruthy();
  });

  it('reveals the true delivery state to the account owner (?token= redemption failure)', async () => {
    const { ApiError } = await import('../../services/apiClient');
    verifyEmailMock.mockRejectedValue(new ApiError('This link has already been used.', 'EMAIL_VERIFICATION_INVALID', 400));
    signIn({ ...baseUser, is_verified: false });

    renderAt('/verify-email?token=stale-token');
    await waitFor(() => expect(screen.getByText(/link not usable/i)).toBeTruthy());
    expect(screen.getByText(/already been used/i)).toBeTruthy();
    expect(screen.getByText(/valid for 24 hours and can be used once/i)).toBeTruthy();
  });
});

describe('invitation acceptance exposes no role field', () => {
  it('renders the invited role read-only from the server preview', async () => {
    previewInviteMock.mockResolvedValue({
      status: 'pending',
      valid: true,
      email_masked: 'i***@gmail.com',
      brand_name: 'Atelier Cairo',
      role: 'brand_staff',
      expires_at: '2026-09-22T00:00:00Z',
    });
    renderAt('/invite?token=inv-123');
    await waitFor(() => expect(screen.getByText(/Atelier Cairo/i)).toBeTruthy());
    expect(screen.getByText('brand_staff')).toBeTruthy();
    expect(screen.queryByRole('combobox')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Redirect safety + reviewer-visible verification truth (Phase 3–6 additions)
// ---------------------------------------------------------------------------

describe('no route honours an attacker-supplied redirect target', () => {
  beforeEach(() => {
    useAuthStore.setState({ user: null, isAuthenticated: false, hasAttemptedBootstrap: true });
    listApplicationsMock.mockResolvedValue([]);
  });

  it('ignores ?next / ?redirect / ?returnUrl on a lifecycle route', () => {
    const before = window.location.href;
    renderAt('/verify-email?next=https://evil.example&redirect=//evil.example&returnUrl=javascript:alert(1)');

    // The screen renders normally and nothing navigated away from the SPA.
    expect(screen.getByRole('heading', { name: /confirm your email address/i })).toBeTruthy();
    expect(window.location.href).toBe(before);
    expect(screen.queryByText(/evil\.example/i)).toBeNull();
  });

  it('ignores a hostile redirect target on the reset route too', () => {
    renderAt('/reset-password?token=abc123&next=//evil.example');
    expect(screen.getByText(/choose a new password/i)).toBeTruthy();
    expect(screen.queryByText(/evil\.example/i)).toBeNull();
  });
});

describe('the reviewer sees the applicant verification truth', () => {
  it('warns that no address could be verified when the deployment cannot send mail', async () => {
    const { adminPartnerService } = await import('../../services/apiServices');
    (adminPartnerService.list as any).mockResolvedValue({
      items: [
        {
          id: 42,
          status: 'pending',
          brand_name: 'Unverifiable Atelier',
          market: 'EG',
          contact_name: 'Applicant',
          contact_email: 'applicant@example.com',
          submitted_at: '2026-09-19T00:00:00Z',
          applicant_email_verified: false,
          applicant_verification_available: false,
        },
      ],
      count: 1,
    });

    signIn({
      ...baseUser,
      role: 'admin',
      onboarding: {
        account_state: 'ACTIVE',
        role: 'admin',
        registration_intent: 'consumer',
        email_verified: true,
        is_active: true,
        profile_completed: true,
        partner_application_status: null,
        partner_access: 'none',
        next_action: { type: 'none', route: '/admin', label: 'Open platform governance' },
        allowed_areas: ['consumer', 'admin'],
      },
    });
    renderAt('/admin/partners');
    await waitFor(() =>
      expect(screen.getByText(/no address could be verified/i)).toBeTruthy()
    );
  });
});
