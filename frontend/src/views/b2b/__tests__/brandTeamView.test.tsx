import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { I18nextProvider } from 'react-i18next';
import i18n from '../../../i18n/i18n';
import BrandTeamView from '../BrandTeamView';
import BrandTeamAcceptView from '../BrandTeamAcceptView';
import { membersService, type BrandTeamMember, type BrandTeamInvitation } from '../../../services/apiServices';
import { ApiError } from '../../../services/apiClient';
import { useAuthStore } from '../../../stores/authStore';

vi.mock('../../../services/apiServices', () => ({
  membersService: {
    myMemberships: vi.fn(),
    listMembers: vi.fn(),
    listInvitations: vi.fn(),
    invite: vi.fn(),
    revokeInvitation: vi.fn(),
    resendInvitation: vi.fn(),
    changeRole: vi.fn(),
    removeMember: vi.fn(),
    accept: vi.fn(),
  },
  authService: { getMe: vi.fn(), logout: vi.fn() },
}));

const OWNER = { id: 1, email: 'ada@brand.test', full_name: 'Ada', role: 'brand_owner' };
const ownerIdentity = (role: 'owner' | 'manager' | 'staff' = 'owner') =>
  useAuthStore.setState({
    user: { ...OWNER, role: role === 'owner' ? 'brand_owner' : role === 'manager' ? 'brand_manager' : 'consumer' } as never,
    isAuthenticated: true,
    hasAttemptedBootstrap: true,
    brandMemberships: [{ brand_id: 7, brand_name: 'Atelier Noir', slug: 'atelier-noir', role, status: 'active' }],
    brandMembershipsStatus: 'ready',
  });

const MEMBERS: BrandTeamMember[] = [
  { id: 11, brand_id: 7, user_id: 1, full_name: 'Ada', email: 'ada@brand.test', role: 'owner', status: 'active', created_at: '2026-01-01T00:00:00Z', revoked_at: null },
  { id: 12, brand_id: 7, user_id: 2, full_name: 'Sam Staff', email: 'sam@brand.test', role: 'staff', status: 'active', created_at: '2026-02-01T00:00:00Z', revoked_at: null },
];
const INVITES: BrandTeamInvitation[] = [
  { id: 21, brand_id: 7, email: 'grace@corp.test', role: 'manager', status: 'pending', created_at: '2026-03-01T00:00:00Z', expires_at: '2026-03-08T00:00:00Z' },
];

const renderView = (route = '/b2b/team') =>
  render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="/b2b/team" element={<BrandTeamView />} />
          <Route path="/b2b/team/accept" element={<BrandTeamAcceptView />} />
        </Routes>
      </MemoryRouter>
    </I18nextProvider>,
  );

beforeEach(() => {
  vi.clearAllMocks();
  ownerIdentity('owner');
  vi.mocked(membersService.listMembers).mockResolvedValue(MEMBERS);
  vi.mocked(membersService.listInvitations).mockResolvedValue(INVITES);
  vi.mocked(membersService.myMemberships).mockResolvedValue([
    { brand_id: 7, brand_name: 'Atelier Noir', slug: 'atelier-noir', role: 'owner', status: 'active' },
  ]);
});

describe('BrandTeamView — owner surface', () => {
  it('renders real membership data and offers owner controls', async () => {
    renderView();
    expect(await screen.findByText('Sam Staff')).toBeTruthy();
    expect(screen.getByText('grace@corp.test')).toBeTruthy();
    expect(screen.getByRole('button', { name: /invite member/i })).toBeTruthy();
    expect(screen.getAllByRole('combobox').length).toBe(2); // one role select per member row
  });

  it('role changes POST the server endpoint and refresh the list', async () => {
    vi.mocked(membersService.changeRole).mockResolvedValue(MEMBERS[1]);
    renderView();
    const select = await screen.findByLabelText(/Role for Sam Staff/i);
    fireEvent.change(select, { target: { value: 'manager' } });
    await waitFor(() => expect(membersService.changeRole).toHaveBeenCalledWith(12, 'manager'));
    await waitFor(() => expect(membersService.listMembers).toHaveBeenCalledTimes(2));
  });

  it('surfaces the server LAST_ACTIVE_OWNER refusal verbatim on a demotion', async () => {
    vi.mocked(membersService.changeRole).mockRejectedValue(
      new ApiError('last owner', 'LAST_ACTIVE_OWNER', 409),
    );
    renderView();
    const select = await screen.findByLabelText(/Role for Ada/i);
    fireEvent.change(select, { target: { value: 'staff' } });
    expect(await screen.findByText(/at least one active owner/i)).toBeTruthy();
  });

  it('invite dialog sends email + role and reports the queued outcome', async () => {
    vi.mocked(membersService.invite).mockResolvedValue(INVITES[0]);
    renderView();
    fireEvent.click(await screen.findByRole('button', { name: /invite member/i }));
    fireEvent.change(screen.getByLabelText(/work email/i), { target: { value: 'new@corp.test' } });
    fireEvent.change(screen.getByLabelText(/tenant role/i), { target: { value: 'staff' } });
    fireEvent.click(screen.getByRole('button', { name: /send invitation/i }));
    await waitFor(() =>
      expect(membersService.invite).toHaveBeenCalledWith({ email: 'new@corp.test', role: 'staff' }),
    );
    expect(await screen.findByText(/queued for delivery/i)).toBeTruthy();
  });

  it('removal is confirm-gated and DELETEs the membership id', async () => {
    vi.mocked(membersService.removeMember).mockResolvedValue({ status: 'revoked', id: 12 });
    renderView();
    // Second row (Sam) — Ada is "You"; owner removal of self goes through the
    // same confirm gate, so scope the query to Sam's button.
    const removeButtons = await screen.findAllByRole('button', { name: 'Remove' });
    fireEvent.click(removeButtons[1]);
    fireEvent.click(screen.getByRole('button', { name: /remove access/i }));
    await waitFor(() => expect(membersService.removeMember).toHaveBeenCalledWith(12));
    expect(await screen.findByText(/access ended with this request/i)).toBeTruthy();
  });
});

describe('BrandTeamView — role-gated surfaces', () => {
  it('staff sees a read-only roster without the invitations section', async () => {
    ownerIdentity('staff');
    renderView();
    expect(await screen.findByText('Sam Staff')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /invite member/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /remove/i })).toBeNull();
    expect(screen.queryByRole('combobox')).toBeNull();
    expect(screen.getByText(/team changes are owner-only/i)).toBeTruthy();
    expect(screen.queryByText(/pending invitations/i)).toBeNull();
  });

  it('manager sees invitations but no mutating controls', async () => {
    ownerIdentity('manager');
    vi.mocked(membersService.myMemberships).mockResolvedValue([
      { brand_id: 7, brand_name: 'Atelier Noir', slug: 'atelier-noir', role: 'manager', status: 'active' },
    ]);
    renderView();
    expect(await screen.findByText('grace@corp.test')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /^resend link$/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /^revoke$/i })).toBeNull();
    expect(screen.getByText(/only owners can change it/i)).toBeTruthy();
  });

  it('per-section load failures stay isolated and retryable', async () => {
    vi.mocked(membersService.listMembers).mockRejectedValue(new ApiError('boom', 'API_ERROR', 500));
    renderView();
    expect(await screen.findByText(/couldn.t load the member list/i)).toBeTruthy();
    // invitations section still rendered its real row
    expect(screen.getByText('grace@corp.test')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /retry/i }));
    await waitFor(() => expect(membersService.listMembers).toHaveBeenCalledTimes(2));
  });
});

describe('BrandTeamAcceptView — public acceptance journey', () => {
  it('accepted invitation flips to the success state and refreshes tenant identity', async () => {
    vi.mocked(membersService.accept).mockResolvedValue({ brand_id: 7, role: 'manager', already_member: false });
    renderView('/b2b/team/accept?token=tok-123');
    await waitFor(() => expect(membersService.accept).toHaveBeenCalledWith('tok-123'));
    expect(await screen.findByText(/you’re on the team/i)).toBeTruthy();
    expect(screen.getByRole('link', { name: /open brand workspace/i })).toBeTruthy();
  });

  it('an invalid/expired/revoked token renders the uniform refusal', async () => {
    vi.mocked(membersService.accept).mockRejectedValue(new ApiError('nope', 'INVITATION_NOT_APPLICABLE', 400));
    renderView('/b2b/team/accept?token=tok-expired');
    expect(await screen.findByText(/link can’t be used/i)).toBeTruthy();
    expect(screen.getByText(/ask a brand owner to send a new link/i)).toBeTruthy();
  });

  it('multi-brand collision gets its own honest explanation', async () => {
    vi.mocked(membersService.accept).mockRejectedValue(new ApiError('multi', 'MULTI_BRAND_NOT_SUPPORTED', 409));
    renderView('/b2b/team/accept?token=tok-2');
    expect(await screen.findByText(/already has a brand/i)).toBeTruthy();
  });

  it('anonymous visitors see the sign-in gateway, not an error', async () => {
    useAuthStore.setState({ isAuthenticated: false, user: null, hasAttemptedBootstrap: true, brandMemberships: null, brandMembershipsStatus: 'idle' });
    vi.mocked(membersService.accept).mockRejectedValue(new ApiError('auth', 'AUTH_REQUIRED', 401));
    renderView('/b2b/team/accept?token=tok-anon');
    expect(await screen.findByText(/sign in to accept/i)).toBeTruthy();
    expect(membersService.accept).not.toHaveBeenCalled();
  });

  it('a link without a token never calls the API', async () => {
    renderView('/b2b/team/accept');
    expect(await screen.findByText(/nothing to accept/i)).toBeTruthy();
    expect(membersService.accept).not.toHaveBeenCalled();
  });
});
