import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { AuthShell, AuthButton, AuthInput, AuthNote } from './AuthShell';
import { authService } from '../../services/apiServices';
import { useAuthStore } from '../../stores/authStore';
import { ApiError } from '../../services/apiClient';

type Phase = 'idle' | 'verifying' | 'verified' | 'failed';

/**
 * /verify-email — the destination of every verification email.
 *
 * Before this route existed the link fell through the SPA catch-all to `/`, so
 * users believed they had verified when nothing had happened. Two modes:
 *   ?token=…        redeem the link (server-side, single use)
 *   no token        "check your inbox" + resend, with the provider's REAL
 *                   delivery status for the signed-in account (no fake
 *                   "we sent you an email" claim).
 */
export const VerifyEmailView: React.FC = () => {
  const [params] = useSearchParams();
  const token = params.get('token');
  const { user, fetchMe } = useAuthStore();

  const [phase, setPhase] = useState<Phase>(token ? 'verifying' : 'idle');
  const [message, setMessage] = useState<string>('');
  const [email, setEmail] = useState(user?.email || '');
  const [resending, setResending] = useState(false);
  const [resendResult, setResendResult] = useState<string | null>(null);
  const [delivery, setDelivery] = useState<{
    status: string;
    accepted: boolean;
    error_class?: string | null;
    provider_configured?: boolean;
  } | null>(null);
  const [providerConfigured, setProviderConfigured] = useState<boolean | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        await authService.verifyEmail(token);
        if (cancelled) return;
        setPhase('verified');
        setMessage('Your email address is confirmed. Thank you!');
        fetchMe();
      } catch (err) {
        if (cancelled) return;
        const apiErr = err as ApiError;
        setPhase('failed');
        setMessage(apiErr?.message || 'This verification link could not be used.');
        if (apiErr?.code === 'FEATURE_NOT_CONFIGURED') {
          setProviderConfigured(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, fetchMe]);

  const loadDelivery = async () => {
    try {
      const status = await authService.getEmailStatus('email_verification');
      setDelivery(status);
    } catch {
      setDelivery(null);
    }
  };

  useEffect(() => {
    if (!token && user) loadDelivery();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, user?.id]);

  const handleResend = async (e: React.FormEvent) => {
    e.preventDefault();
    setResending(true);
    setResendResult(null);
    try {
      const res = await authService.requestEmailVerification(email);
      setResendResult(
        `Request accepted (${res.status}). If the address needs verification, a confirmation link has been sent.`
      );
      loadDelivery();
    } catch (err) {
      const apiErr = err as ApiError;
      if (apiErr?.code === 'FEATURE_NOT_CONFIGURED') {
        setProviderConfigured(false);
        setResendResult(
          'Email delivery is not configured in this environment, so no verification email can be sent. This is a known, honest limitation — nothing was sent.'
        );
      } else {
        setResendResult(apiErr?.message || 'We could not process that request.');
      }
    } finally {
      setResending(false);
    }
  };

  if (token) {
    return (
      <AuthShell
        eyebrow="Email verification"
        title={phase === 'verified' ? 'Email confirmed' : phase === 'failed' ? 'Link not usable' : 'Verifying your email…'}
        tone={phase === 'verified' ? 'success' : phase === 'failed' ? 'danger' : 'neutral'}
      >
        {phase === 'verifying' && <AuthNote>Checking your one-time link with the server…</AuthNote>}
        {phase === 'verified' && (
          <>
            <AuthNote tone="success">{message}</AuthNote>
            <a href="/" className="block text-center text-[#C5A059] hover:underline">
              Continue to CONFIT →
            </a>
          </>
        )}
        {phase === 'failed' && (
          <>
            <AuthNote tone="error">{message}</AuthNote>
            <p className="text-slate-400">
              Verification links are valid for 24 hours and can be used once. Request a fresh one below.
            </p>
            {user ? (
              <AuthButton onClick={() => { setPhase('idle'); }}>Request a new link</AuthButton>
            ) : (
              <a href="/verify-email" className="block text-center text-[#C5A059] hover:underline">
                Request a new link →
              </a>
            )}
          </>
        )}
      </AuthShell>
    );
  }

  const providerMissing = delivery?.provider_configured === false || providerConfigured === false;

  return (
    <AuthShell eyebrow="Email verification" title="Confirm your email address">
      {providerMissing ? (
        <AuthNote tone="error">
          Email delivery is not configured on this deployment, so verification emails cannot be sent — and no
          verification has taken place. Any account created here is marked verified only because there is no channel
          to check the address; once an operator configures a provider, verify explicitly.
        </AuthNote>
      ) : (
        <p className="text-slate-400">
          Enter the address you registered with and we will send a fresh single-use confirmation link (valid 24 hours).
        </p>
      )}
      <form onSubmit={handleResend} className="space-y-3">
        <AuthInput
          label="Email address"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          autoComplete="email"
        />
        <AuthButton type="submit" disabled={resending}>
          {resending ? 'Requesting…' : 'Send verification link'}
        </AuthButton>
      </form>
      {resendResult && <AuthNote tone="info">{resendResult}</AuthNote>}
      {delivery && (
        <AuthNote tone={delivery.accepted ? 'success' : 'error'}>
          Last delivery attempt for your account: <strong>{delivery.status}</strong>
          {delivery.error_class ? ` (${delivery.error_class})` : ''}
          {delivery.accepted
            ? ' — the mail server accepted the message.'
            : ' — no message was accepted by the mail server.'}
        </AuthNote>
      )}
    </AuthShell>
  );
};
