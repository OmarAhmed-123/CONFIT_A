import React, { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { AuthShell, AuthButton, AuthInput, AuthNote } from './AuthShell';
import { invitationService } from '../../services/apiServices';
import { useAuthStore } from '../../stores/authStore';
import { ApiError, setAuthTokens } from '../../services/apiClient';

/**
 * /invite?token=… — accept a brand invitation.
 *
 * The role and the brand come from the server-issued invitation row; the
 * invitee only supplies their own name/password when no account exists yet.
 * There is no field on this page that could request a different role.
 */
export const InviteAcceptView: React.FC = () => {
  const [params] = useSearchParams();
  const token = params.get('token') || '';
  const navigate = useNavigate();
  const { fetchMe, isAuthenticated, user } = useAuthStore();

  const [preview, setPreview] = useState<{
    status: string;
    valid: boolean;
    email_masked?: string;
    brand_name?: string;
    role?: string;
    expires_at?: string;
  } | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    invitationService
      .preview(token)
      .then(setPreview)
      .catch((err) => setPreviewError((err as ApiError)?.message || 'We could not check this invitation.'));
  }, [token]);

  const needsAccount = preview?.valid === true && (!isAuthenticated || !user);

  const accept = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await invitationService.accept({
        token,
        ...(needsAccount ? { full_name: fullName, password } : {}),
      });
      // Mirror the standard sign-in path: the session lives in an httpOnly
      // cookie set by the server; only the profile snapshot is cached locally.
      setAuthTokens(res.access_token, res.refresh_token);
      localStorage.setItem('confit_user', JSON.stringify(res.user));
      await fetchMe();
      navigate('/b2b', { replace: true });
    } catch (err) {
      setError((err as ApiError)?.message || 'This invitation could not be accepted.');
    } finally {
      setBusy(false);
    }
  };

  if (!token) {
    return (
      <AuthShell eyebrow="Brand invitation" title="Invitation link required" tone="warning">
        <AuthNote tone="error">This page needs the one-time link from your invitation email.</AuthNote>
      </AuthShell>
    );
  }

  const invalidStates: Record<string, string> = {
    accepted: 'This invitation has already been accepted. Sign in to open the brand portal.',
    revoked: 'This invitation was revoked by the brand owner. Ask them to send a new one.',
    expired: 'This invitation has expired. Ask the brand owner to send a new one.',
    unknown: 'This invitation link is not valid.',
  };

  return (
    <AuthShell
      eyebrow="Brand invitation"
      title={preview?.valid ? `Join ${preview.brand_name ?? 'a brand workspace'}` : 'Invitation'}
      tone={preview?.valid ? 'success' : 'warning'}
    >
      {previewError && <AuthNote tone="error">{previewError}</AuthNote>}
      {!preview && !previewError && <AuthNote>Checking this invitation…</AuthNote>}
      {preview && !preview.valid && (
        <>
          <AuthNote tone="error">{invalidStates[preview.status] || 'This invitation cannot be used.'}</AuthNote>
          <Link to="/" className="block text-center text-[#C5A059] hover:underline">Go to CONFIT →</Link>
        </>
      )}
      {preview?.valid && (
        <>
          <AuthNote>
            Invitation for <strong>{preview.email_masked}</strong> — role <strong>{preview.role}</strong>
            {preview.expires_at ? ` · expires ${new Date(preview.expires_at).toLocaleString()}` : ''}
          </AuthNote>
          <form onSubmit={accept} className="space-y-3">
            {needsAccount ? (
              <>
                <p className="text-slate-400">
                  No CONFIT account exists for this address yet — create it here. The workspace and role below were
                  assigned by the inviter, not by this form.
                </p>
                <AuthInput
                  label="Full name"
                  required
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  autoComplete="name"
                />
                <AuthInput
                  label="Choose a password"
                  type="password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="new-password"
                />
              </>
            ) : (
              <p className="text-slate-400">
                You are signed in as <strong>{user?.email}</strong>. Accepting links this account to the workspace.
              </p>
            )}
            {error && <AuthNote tone="error">{error}</AuthNote>}
            <AuthButton type="submit" disabled={busy}>{busy ? 'Accepting…' : 'Accept invitation'}</AuthButton>
          </form>
        </>
      )}
    </AuthShell>
  );
};
