import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { AuthShell, AuthButton, AuthInput, AuthNote } from './AuthShell';
import { authService } from '../../services/apiServices';
import { ApiError } from '../../services/apiClient';

/**
 * /forgot-password — request a reset link.
 *
 * The response is intentionally non-committal (identical for known and unknown
 * addresses), so the copy stays conditional: we never tell an anonymous
 * visitor "we sent an email" when the account may not exist. When the
 * deployment has no email provider the server answers 501 and we say exactly
 * that instead of pretending.
 */
export const ForgotPasswordView: React.FC = () => {
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{ tone: 'info' | 'success' | 'error'; text: string } | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setResult(null);
    try {
      const res = await authService.forgotPassword(email);
      setResult({
        tone: 'info',
        text: res.message || 'If an account exists with that email, reset instructions have been sent.',
      });
    } catch (err) {
      const apiErr = err as ApiError;
      if (apiErr?.code === 'FEATURE_NOT_CONFIGURED') {
        setResult({
          tone: 'error',
          text: 'Password reset by email is not configured on this deployment, so no email was sent. An operator must configure EMAIL_PROVIDER before this flow can work.',
        });
      } else {
        setResult({ tone: 'error', text: apiErr?.message || 'We could not process that request.' });
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell eyebrow="Account recovery" title="Reset your password">
      <p className="text-slate-400">
        Enter your account email. If it matches an account, you will receive a single-use link valid for 30 minutes.
      </p>
      <form onSubmit={submit} className="space-y-3">
        <AuthInput
          label="Email address"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
        />
        <AuthButton type="submit" disabled={submitting}>{submitting ? 'Sending…' : 'Send reset link'}</AuthButton>
      </form>
      {result && <AuthNote tone={result.tone === 'error' ? 'error' : 'info'}>{result.text}</AuthNote>}
      <p className="text-center text-slate-400">
        Remembered it? <Link to="/" className="text-[#C5A059] hover:underline">Sign in</Link>
      </p>
    </AuthShell>
  );
};
